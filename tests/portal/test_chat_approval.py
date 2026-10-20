"""A staged change is approved or rejected in the chat with the AI assistant, as on the Pending changes page (VOI-246, make test-db).

The Commands run on the SDK's worker threads with their own database connection, so these tests commit (transaction=True).
"""

# pyright: basic
# (django-stubs types model fields for mypy's plugin; strict pyright cannot read them)

import logging
from typing import Any

import pytest

from portal.accounts import views
from portal.accounts.models import Module, PendingChange
from tests.portal.helpers import business_with_login
from tests.portal.test_agent_endpoint import a_token, ask
from tests.portal.test_pending_changes import ADDRESS, audited, decided

pytestmark = [pytest.mark.db, pytest.mark.django_db(transaction=True)]


def run(secret: str, command: str, **arguments: Any) -> dict[str, Any]:
    answer = ask("tools/call", {"name": command, "arguments": arguments}, secret)
    assert answer.status_code == 200, answer.content
    return answer.json()["result"]


def text(answer: dict[str, Any]) -> str:
    return answer["content"][0]["text"]


def staged_removal(email: str = "user-a@example.com") -> tuple[Any, str, Module, int]:
    business, client = business_with_login(email, "Owner's Salon")
    module = Module.objects.create(business=business, name="Bookings", url=ADDRESS)
    secret = a_token(business, "full")
    staged = run(secret, "remove_module", name="Bookings")["structuredContent"]
    assert "approve_change" in staged["next"] and "/changes/" in staged["next"]
    return client, secret, module, staged["change"]


def test_a_change_is_listed_and_approved_in_the_chat_once(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="portal.audit")
    _, secret, module, change = staged_removal()
    waiting = run(a_token(module.business, "read"), "list_pending_changes")[
        "structuredContent"
    ]["result"]
    assert [(w["change"], w["preview"], w["risk_level"]) for w in waiting] == [
        (change, "Remove the Module “Bookings”", "medium")
    ]
    answer = run(secret, "approve_change", change=change)
    assert (
        not answer.get("isError")
        and answer["structuredContent"]["outcome"] == "applied"
    )
    assert text(answer).find(views.OUTCOMES["applied"]) >= 0
    assert not Module.objects.filter(pk=module.pk).exists()
    again = run(secret, "approve_change", change=change)
    assert again.get("isError") and views.OUTCOMES["already_decided"] in text(again)
    token = PendingChange.objects.get().token.pk
    assert audited(caplog)[-1].endswith(f"by token {token} in the chat")


def test_a_change_rejected_in_the_chat_never_applies() -> None:
    client, secret, module, change = staged_removal()
    assert (
        run(secret, "reject_change", change=change)["structuredContent"]["outcome"]
        == "rejected"
    )
    assert Module.objects.filter(pk=module.pk).exists()
    assert views.OUTCOMES["already_decided"] in decided(
        client, PendingChange.objects.get(), "approve"
    )


def test_another_businesss_change_answers_like_an_unknown_one() -> None:
    _, _, module, change = staged_removal()
    other, _ = business_with_login("user-b@example.com", "Owner B's Bikes")
    theirs = a_token(other, "full")
    for command in ("approve_change", "reject_change"):
        mine = run(theirs, command, change=change)
        unknown = run(theirs, command, change=change + 1000)
        assert mine.get("isError") and text(mine) == text(unknown)
    assert run(theirs, "list_pending_changes")["structuredContent"]["result"] == []
    assert Module.objects.filter(pk=module.pk).exists()
    assert PendingChange.objects.get().decision == ""


def test_a_read_only_token_cannot_decide() -> None:
    _, _, module, change = staged_removal()
    read = a_token(module.business, "read")
    for command in ("approve_change", "reject_change"):
        assert text(run(read, command, change=change)) == f"Unknown tool: {command}"
    assert PendingChange.objects.get().decision == ""
