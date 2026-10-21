# pyright: basic
# (django-stubs types model fields for mypy's plugin; strict pyright cannot read them)
import getpass
import logging
from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from portal.accounts.models import CallLog
from portal.accounts.prod_script import check_target

audit = logging.getLogger("portal.audit")


class Command(BaseCommand):
    help = "Delete the Call logs past their 30 days (VOI-157), run daily by a Dokploy schedule. Dry run unless --execute; no reviewed hash, the one exemption in .claude/rules/prod-scripts.md."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--target",
            required=True,
            help="where this runs: local or production; must match ENVIRONMENT",
        )
        parser.add_argument("--execute", action="store_true")

    def handle(self, *args: Any, **options: Any) -> None:
        check_target(options)
        self.stdout.write(f"target: {options['target']}")
        if not options["execute"]:
            ids = list(
                CallLog.expired().order_by("pk").values_list("call_id", flat=True)
            )
            self.stdout.write(f"would delete {len(ids)} expired Call log(s): {ids}")
            self.stdout.write("dry run, nothing changed. To delete: --execute")
            return
        deleted = CallLog.delete_expired()
        audit.info(
            "deleted %s expired call logs by %s", deleted, getpass.getuser()
        )  # a count only
        self.stdout.write(f"deleted {deleted} expired Call log(s)")
