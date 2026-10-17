# pyright: basic
# (django-stubs types model fields for mypy's plugin; strict pyright cannot read them)
import getpass
import logging
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from portal.accounts.invite import invite
from portal.accounts.models import clean_email
from portal.accounts.prod_script import check_target, reviewed_digest

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
        check_target(options)
        digest = reviewed_digest(
            self,
            options,
            {"invite": clean_email(options["email"]), "name": options["name"]},
        )
        if digest is None:
            return
        try:
            account = invite(options["name"], options["email"])
        except ValueError as refused:
            raise CommandError(str(refused)) from refused
        audit.info(
            "invited account %s by %s, plan %s", account.pk, getpass.getuser(), digest
        )  # ids only: no email or name in logs
        self.stdout.write(f"invited 1 Business, plan {digest}")
