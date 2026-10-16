# pyright: basic
# (django-stubs types model fields for mypy's plugin; strict pyright cannot read them)
import getpass
import hashlib
import json
import logging
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser

from portal.accounts.models import Business, clean_email

audit = logging.getLogger("portal.audit")


class Command(BaseCommand):
    help = "Switch a Business on or off and set its daily call limits: the one way they change. Dry run unless --execute with the reviewed hash (.claude/rules/prod-scripts.md)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("email", help="the Business's account email")
        parser.add_argument("--enabled", choices=("on", "off"))
        parser.add_argument("--max-calls-per-day", type=int)
        parser.add_argument("--max-minutes-per-day", type=int)
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
        try:
            business = Business.objects.get(
                account__email=clean_email(options["email"])
            )
        except Business.DoesNotExist:
            raise CommandError("no Business has that email") from None
        wanted: dict[str, Any] = {}
        if options["enabled"]:
            wanted["enabled"] = options["enabled"] == "on"
        for field in ("max_calls_per_day", "max_minutes_per_day"):
            if options[field] is not None:
                if options[field] < 0:
                    raise CommandError(f"{field} must not be negative")
                wanted[field] = options[field]
        if not wanted:
            raise CommandError(
                "nothing to change: give --enabled, --max-calls-per-day or --max-minutes-per-day"
            )
        plan = json.dumps(
            {
                "target": options["target"],
                "business": business.pk,
                "change": {k: [getattr(business, k), v] for k, v in wanted.items()},
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
        Business.objects.filter(pk=business.pk).update(**wanted)
        audit.info(
            "configured business %s by %s, plan %s",
            business.pk,
            getpass.getuser(),
            digest,
        )  # ids only: no email or name in logs
        self.stdout.write(f"configured 1 Business, plan {digest}")
