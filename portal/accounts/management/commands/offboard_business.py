# pyright: basic
# (django-stubs types model fields for mypy's plugin; strict pyright cannot read them)
import getpass
import logging
from decimal import Decimal
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import connection, transaction
from django.db.models import CharField, Value
from django.db.models.functions import Cast, Concat

from portal.accounts.models import (
    AccessToken,
    Account,
    Business,
    CallRecord,
    Module,
    OAuthConnection,
    PendingChange,
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
        connections = list(
            OAuthConnection.objects.filter(business=business, revoked_at__isnull=True)
        )
        labels = AccessToken.objects.filter(business=business)
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
                "sign-in connections to revoke": str(len(connections)),
                # Revoking cancels them (AccessToken.revoke, VOI-239).
                "pending changes to cancel": str(
                    PendingChange.objects.filter(token__in=tokens, decision="").count()
                ),
                "access token labels to blank": str(labels.count()),
                "modules to delete": str(modules.count()),
                "call records kept": str(
                    CallRecord.objects.filter(business=business).count()
                ),
            },
        )
        if digest is None:
            return
        with transaction.atomic():
            # The Business first, as an approval and a Command lock it, so none of them waits on another in a ring.
            Business.objects.select_for_update().get(pk=business.pk)
            revoked = list(tokens)
            for token in revoked:
                token.revoke()
            # A sign-in would mint new tokens: its connection ends too (VOI-119).
            for sign_in in connections:
                sign_in.revoke()
            # A label may name a person: the one path that may blank it (migration 0022), once every token is revoked.
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT set_config('voice.offboard_token_labels', 'on', true)"
                )
                blanked = labels.update(
                    label=Concat(Value("Token "), Cast("id", output_field=CharField()))
                )
                cursor.execute(
                    "SELECT set_config('voice.offboard_token_labels', '', true)"
                )
            deleted = Module.remove(modules)
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
            "offboarded business %s (account %s) by %s: %s tokens revoked, %s token labels blanked, %s modules deleted, plan %s",
            business.pk,
            account.pk,
            getpass.getuser(),
            len(revoked),
            blanked,
            deleted,
            digest,
        )  # ids only: no email or name in logs
        self.stdout.write(f"offboarded 1 Business, plan {digest}")
