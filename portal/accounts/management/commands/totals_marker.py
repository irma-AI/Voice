# pyright: basic
# (django-stubs types model fields for mypy's plugin; strict pyright cannot read them)
import getpass
import hashlib
import json
import logging
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import connection, transaction

from portal.accounts.models import Account, clean_email

audit = logging.getLogger("portal.audit")


class Command(BaseCommand):
    help = "Give an Account the totals page, or take it away. The only way the marker changes. Dry run unless --execute with the reviewed hash (.claude/rules/prod-scripts.md)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("email")
        parser.add_argument("--clear", action="store_true", help="take the marker away")
        parser.add_argument(
            "--target",
            required=True,
            help="where this runs: local or production; must match ENVIRONMENT",
        )
        parser.add_argument("--execute", action="store_true")
        parser.add_argument("--approved-hash")

    def handle(self, *args: Any, **options: Any) -> None:
        if options["target"] != settings.ENVIRONMENT:
            raise CommandError(
                f"--target {options['target']} but this process runs in {settings.ENVIRONMENT}"
            )
        email = clean_email(options["email"])
        wanted = not options["clear"]
        account = Account.objects.filter(email=email).first()
        if account is None:
            raise CommandError("no Account has that email")
        plan = json.dumps(
            {
                "target": options["target"],
                "account": email,
                "sees_totals": f"{account.sees_totals} -> {wanted}",
            },
            sort_keys=True,
            indent=1,
        )
        digest = hashlib.sha256(plan.encode()).hexdigest()
        self.stdout.write(f"target: {options['target']}\n{plan}\nplan sha256: {digest}")
        if not options["execute"]:
            self.stdout.write(
                "dry run, nothing changed. After review: --execute --approved-hash=<sha256>"
            )
            return
        if options["approved_hash"] != digest:
            raise CommandError(
                "the plan changed since it was reviewed: review the new dry run"
            )
        with transaction.atomic():
            with connection.cursor() as cursor:
                # Lets this transaction through the trigger in migration 0008.
                cursor.execute(
                    "SELECT set_config('voice.totals_marker_command', 'on', true)"
                )
            Account.objects.filter(pk=account.pk).update(sees_totals=wanted)
            # Closed again at once: inside an outer transaction (a test) the setting would otherwise stay on.
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT set_config('voice.totals_marker_command', 'off', true)"
                )
        audit.info(
            "totals marker of account %s set to %s by %s, plan %s",
            account.pk,
            wanted,
            getpass.getuser(),
            digest,
        )  # ids only: no email in logs
        self.stdout.write(f"changed 1 Account, plan {digest}")
