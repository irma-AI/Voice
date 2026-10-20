# pyright: basic
# (django-stubs types model fields for mypy's plugin; strict pyright cannot read them)
"""Staged changes (VOI-239): a destructive Command records a PendingChange, and only the Business's approval in the Portal
applies it, through the same function the Portal page uses (CLAUDE.md hard rule 2). The database applies each once."""

import logging
from datetime import timedelta
from typing import Any, Literal, assert_never

from django.conf import settings
from django.db import IntegrityError, connection, transaction
from django.db.models import QuerySet
from django.db.models.functions import Now
from django.urls import reverse

from portal.accounts.models import AccessToken, Account, Module, PendingChange

audit = logging.getLogger("portal.audit")

# How long a change waits for approval; migration 0026's trigger holds the same 7 days.
WAITS = timedelta(days=7)

Kind = Literal["remove_module"]
RISK: dict[Kind, Literal["low", "medium", "high"]] = {
    "remove_module": "medium"  # the agent stops using it in calls; adding it again undoes it
}


def preview(change: PendingChange) -> str:
    kind: Kind = change.kind  # pyright: ignore[reportAssignmentType]
    match kind:
        case "remove_module":  # the name is read now: the change keeps only the id, so offboarding leaves no name behind
            name = (
                Module.objects.filter(
                    pk=change.target["module"], business=change.token.business
                )
                .values_list("name", flat=True)
                .first()
            )
            return (
                f"Remove the Module “{name}”"
                if name is not None
                else "Remove a Module that is already gone"
            )
        case _:
            assert_never(kind)


def stage(token: AccessToken, kind: Kind, target: dict[str, Any]) -> dict[str, Any]:
    """The one way a change is staged: it is stored undecided, and the answer tells the agent nothing has changed yet."""
    change = PendingChange.objects.create(token=token, kind=kind, target=target)
    transaction.on_commit(  # the Command's transaction may still roll back
        lambda: audit.info(
            "staged pending change %s (%s) for business %s by token %s",
            change.pk,
            kind,
            token.business.pk,
            token.pk,
        )
    )
    page = settings.PORTAL_URL.rstrip("/") + reverse("pending_changes")
    return {
        "staged": True,
        "change": change.pk,
        "preview": preview(change),
        "risk_level": RISK[kind],
        "next": f"Nothing has changed yet. Ask the Business to approve it at {page}; it expires in {WAITS.days} days.",
    }


def waiting(account: Account) -> QuerySet[PendingChange]:
    """The Business's changes still waiting for a decision, oldest first."""
    return PendingChange.objects.filter(
        token__business__account=account,
        decision="",
        staged_at__gt=Now() - WAITS,
        token__revoked_at__isnull=True,  # the database refuses to approve those
    ).order_by("staged_at", "id")


def _apply(change: PendingChange) -> bool:
    """Whether anything changed: what the change names may be gone already (removed on the Modules page)."""
    kind: Kind = change.kind  # pyright: ignore[reportAssignmentType]
    match kind:
        case "remove_module":  # the Modules page's own Remove
            return (
                Module.remove(
                    Module.objects.filter(
                        pk=change.target["module"], business=change.token.business
                    )
                )
                > 0
            )
        case _:
            assert_never(kind)


Decided = Literal["applied", "nothing_left", "rejected", "refused"]


def decide(
    change: PendingChange, account: Account, decision: Literal["approved", "rejected"]
) -> Decided:
    """The one way a change is decided, only by its own Business. "refused" when it was already decided or, for an approval,
    has expired or its token was revoked (the database refuses those), or is another Business's."""
    applied = False
    try:
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute("SELECT set_config('voice.change_decide', 'on', true)")
            decided = PendingChange.objects.filter(
                pk=change.pk, token__business__account=account
            ).update(decision=decision, decided_at=Now())
            cursor.execute("SELECT set_config('voice.change_decide', '', true)")
            if not decided:
                return "refused"
            if decision == "approved":
                applied = _apply(change)
    except IntegrityError as error:
        if "pending_change_" not in str(error):
            raise
        return "refused"
    audit.info(
        "%s pending change %s (%s) for business %s by account %s%s",
        decision,
        change.pk,
        change.kind,
        change.token.business.pk,
        account.pk,
        "" if applied or decision == "rejected" else ": nothing left to change",
    )
    if decision == "rejected":
        return "rejected"
    return "applied" if applied else "nothing_left"
