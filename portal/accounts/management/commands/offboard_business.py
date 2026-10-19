# pyright: basic
# (django-stubs types model fields for mypy's plugin; strict pyright cannot read them)
import getpass
import logging
from decimal import Decimal
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import transaction

from portal.accounts.models import (
    AccessToken,
    Account,
    Business,
    CallRecord,
    Module,
    clean_email,
)
from portal.accounts.prod_script import check_target, reviewed_digest

audit = logging.getLogger("portal.audit")


class Command(BaseCommand):
    help = "Offboard a Business: empties its personal data and closes its login; its Call records stay, keyed by number. Dry run unless --execute with the reviewed hash (.claude/rules/prod-scripts.md)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("email")
        parser.add_argument(
            "--target",
            required=True,
            help="where this runs: local or production; must match ENVIRONMENT",
        )
        parser.add_argument("--execute", action="store_true")
        parser.add_argument("--approved-hash")

    def handle(self, *args: Any, **options: Any) -> None:
        check_target(options)
        email = clean_email(options["email"])
        business = (
            Business.objects.select_related("account")
            .filter(account__email=email)
            .first()
        )
        if business is None:
            raise CommandError("no Account with a Business has that email")
        tokens = AccessToken.objects.filter(business=business, revoked_at__isnull=True)
        modules = Module.objects.filter(business=business)
        digest = reviewed_digest(
            self,
            options,
            {
                "offboard": email,
                # What the reviewer recognises: the wrong customer's email still names its own Business here.
                "name now": business.name,
                "website domain now": business.website_domain,
                "account": str(business.account.pk),
                "business": str(business.pk),
                "access tokens to revoke": str(tokens.count()),
                "modules to delete": str(modules.count()),
                "call records kept": str(
                    CallRecord.objects.filter(business=business).count()
                ),
            },
        )
        if digest is None:
            return
        with transaction.atomic():
            revoked = list(tokens)
            for token in revoked:
                token.revoke()
            deleted, _ = modules.delete()
            business.name = f"Business {business.pk}"
            business.instructions = business.website_domain = business.accent = ""
            business.privacy_url = ""
            # Its call link may still sit on the Business's website: it spends nothing more.
            business.daily_budget_usd = Decimal(0)
            business.set_logo(None)
            business.save()
            account: Account = business.account
            # .invalid never resolves (RFC 2606), so no mail can reach it.
            account.email = f"deleted-{account.pk}@invalid"
            account.is_active = False
            account.last_login = None
            account.set_unusable_password()
            account.save()
        audit.info(
            "offboarded business %s (account %s) by %s: %s tokens revoked, %s modules deleted, plan %s",
            business.pk,
            account.pk,
            getpass.getuser(),
            len(revoked),
            deleted,
            digest,
        )  # ids only: no email or name in logs
        self.stdout.write(f"offboarded 1 Business, plan {digest}")
