# pyright: basic
# (django-stubs types model fields for mypy's plugin; strict pyright cannot read them)
import getpass
import hashlib
import json
import logging
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser

from portal.accounts.invite import invite
from portal.accounts.models import clean_email

audit = logging.getLogger("portal.audit")


class Command(BaseCommand):
    help = "Invite a Business: creates its account and emails the link where it sets a password. Dry run unless --execute with the reviewed hash (.claude/rules/prod-scripts.md)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("email")
        parser.add_argument("name")
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
        plan = json.dumps(
            {
                "target": options["target"],
                "invite": clean_email(options["email"]),
                "name": options["name"],
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
        try:
            account = invite(options["name"], options["email"])
        except ValueError as refused:
            raise CommandError(str(refused)) from refused
        audit.info(
            "invited account %s by %s, plan %s", account.pk, getpass.getuser(), digest
        )  # ids only: no email or name in logs
        self.stdout.write(f"invited 1 Business, plan {digest}")
