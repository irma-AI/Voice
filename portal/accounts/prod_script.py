"""The shared steps of a script that changes shared data (.claude/rules/prod-scripts.md)."""

import hashlib
import json
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


def check_target(options: dict[str, Any]) -> None:
    if options["target"] != settings.ENVIRONMENT:
        raise CommandError(
            f"--target {options['target']} but this process runs in {settings.ENVIRONMENT}"
        )


def reviewed_digest(
    command: BaseCommand, options: dict[str, Any], plan: dict[str, str]
) -> str | None:
    """Print the plan and its sha256. Returns the digest when --execute carries the matching hash, None on a dry run."""
    text = json.dumps({"target": options["target"], **plan}, sort_keys=True, indent=1)
    digest = hashlib.sha256(text.encode()).hexdigest()
    command.stdout.write(f"target: {options['target']}\n{text}\nplan sha256: {digest}")
    if not options["execute"]:
        command.stdout.write(
            "dry run, nothing changed. After review: --execute --approved-hash=<sha256>"
        )
        return None
    if options["approved_hash"] != digest:
        raise CommandError(
            "the plan changed since it was reviewed: review the new dry run"
        )
    return digest
