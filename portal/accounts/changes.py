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

from portal.accounts import invite
from portal.accounts.models import (
    LANGUAGES,
    AccessToken,
    Account,
    Business,
    Module,
    PendingChange,
    StagedValues,
    operator_account,
)
from portal.accounts.settings_form import changed

audit = logging.getLogger("portal.audit")

# How long a change waits for approval; migration 0026's trigger holds the same 7 days.
WAITS = timedelta(days=7)

Kind = Literal["remove_module", "change_details", "invite_business"]
RISK: dict[Kind, Literal["low", "medium", "high"]] = {
    "remove_module": "medium",  # the agent stops using it in calls; adding it again undoes it
    "change_details": "high",  # the instructions are what the agent tells every Caller
    "invite_business": "medium",  # an email to someone outside, and an Account that only offboarding closes
}


def _values(change: PendingChange) -> dict[str, Any]:
    staged = StagedValues.objects.filter(change=change).first()
    return staged.values if staged is not None else {}


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
        case (
            "change_details"
        ):  # every value in full: the Business approves exactly what it reads here
            values = _values(change)
            lines = []
            if "name" in values:
                lines.append(f"Change the Business name to “{values['name']}”")
            if "languages" in values:
                names = " and ".join(LANGUAGES[code] for code in values["languages"])
                lines.append(f"Change the languages to {names}")
            if "instructions" in values:
                lines.append(f"Change the instructions to:\n{values['instructions']}")
            return "\n".join(lines) or "Change details that were already decided"
        case "invite_business":
            values = _values(change)
            if not values:
                return "Invite a Business that was already decided"
            return f"Invite “{values['name']}” at {values['email']}"
        case _:
            assert_never(kind)


def stage(
    token: AccessToken,
    kind: Kind,
    target: dict[str, Any],
    values: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """The one way a change is staged: it is stored undecided, and the answer tells the agent nothing has changed yet.
    `values` are what it would write, kept apart from the change (StagedValues) so they can be deleted."""
    change = PendingChange.objects.create(token=token, kind=kind, target=target)
    if values is not None:
        StagedValues.objects.create(change=change, values=values)
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
        case (
            "change_details"
        ):  # the settings page's own form, with the staged values on top
            values = _values(change)
            if not values:
                return False
            business = Business.objects.select_for_update().get(
                pk=change.token.business.pk
            )  # as stored now: the form writes every setting
            form = changed(business, **values)
            if (
                not form.is_valid()
            ):  # a saved setting no longer passes (a rule changed): write none of it
                raise NotApplied("no_longer_fits")
            form.save()
            return True
        case "invite_business":  # the management command's own invite
            values = _values(change)
            if not values:
                return False
            if not operator_account(
                change.token.business.account
            ):  # as agent.is_operator, at approval too
                raise NotApplied("not_operator")
            try:
                invite.invite(values["name"], values["email"])
            except ValueError:  # taken since, or the mail failed: nothing was created, and the change waits
                raise NotApplied("invite_refused") from None
            return True
        case _:
            assert_never(kind)


class NotApplied(Exception):
    """An approval that cannot be made now writes nothing and the change keeps waiting; `outcome` says why on the page."""

    def __init__(self, outcome: "Decided") -> None:
        super().__init__(outcome)
        self.outcome: Decided = outcome


Decided = Literal[
    "applied",
    "nothing_left",
    "rejected",
    "already_decided",
    "cancelled",
    "expired",
    "no_longer_fits",
    "invite_refused",
    "not_operator",
]


def refusal(change: PendingChange) -> Decided:
    """Why the database refused a decision, read back from the change as it now stands."""
    now = PendingChange.objects.get(pk=change.pk).decision
    if now == "cancelled":
        return "cancelled"
    return "already_decided" if now else "expired"


def decide(
    change: PendingChange, account: Account, decision: Literal["approved", "rejected"]
) -> Decided:
    """The one way a change is decided, only by its own Business (the caller has checked it is). The database refuses a change
    already decided, cancelled by its token's revoke, or for an approval, expired: the answer says which."""
    applied = False
    try:
        with transaction.atomic(), connection.cursor() as cursor:
            # The Business first, then the change, as a Command and offboarding lock them, so none waits on another in a ring.
            list(Business.objects.select_for_update().filter(account=account))
            cursor.execute("SELECT set_config('voice.change_decide', 'on', true)")
            decided = PendingChange.objects.filter(
                pk=change.pk, token__business__account=account
            ).update(decision=decision, decided_at=Now())
            cursor.execute("SELECT set_config('voice.change_decide', '', true)")
            if not decided:
                return refusal(change)
            if decision == "approved":
                applied = _apply(change)
            StagedValues.objects.filter(change=change).delete()
    except IntegrityError as error:
        if "pending_change_" not in str(error):
            raise
        return refusal(change)
    except NotApplied as not_now:
        return not_now.outcome
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
