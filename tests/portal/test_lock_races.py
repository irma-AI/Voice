"""Two connections at once on a staged change (VOI-246, make test-db): no deadlock, and the change is decided once.

Each race holds the other side's locks in a thread for a moment while the Command runs, the way two requests overlap in
production. Commands run on the SDK's worker threads with their own database connection, so these tests commit.
"""

# pyright: basic
# (django-stubs types model fields for mypy's plugin; strict pyright cannot read them)

import threading
import time
from collections.abc import Callable
from typing import Any

import pytest
from django.db import connection, transaction

from portal.accounts.models import (
    AccessToken,
    Business,
    CommandRecord,
    Module,
    PendingChange,
)
from tests.portal.helpers import business_with_login
from tests.portal.test_agent_endpoint import a_token, ask
from tests.portal.test_pending_changes import ADDRESS

pytestmark = [pytest.mark.db, pytest.mark.django_db(transaction=True)]


def run(secret: str, command: str, **arguments: Any) -> dict[str, Any]:
    answer = ask("tools/call", {"name": command, "arguments": arguments}, secret)
    assert answer.status_code == 200, answer.content
    return answer.json()["result"]


def staged() -> tuple[Business, str, int]:
    business, _ = business_with_login("user-a@example.com", "Owner's Salon")
    Module.objects.create(business=business, name="Bookings", url=ADDRESS)
    secret = a_token(business, "full")
    change = run(secret, "remove_module", name="Bookings")["structuredContent"][
        "change"
    ]
    return business, secret, change


def alongside(
    other: Callable[[], None], command: Callable[[], dict[str, Any]]
) -> dict[str, Any]:
    """Runs `other` in its own connection, started a moment before `command`; fails on any error either side raises."""
    errors: list[str] = []

    def side() -> None:
        try:
            other()
        except Exception as error:  # noqa: BLE001  any error is the finding
            errors.append(repr(error))
        finally:
            connection.close()

    thread = threading.Thread(target=side)
    thread.start()
    time.sleep(0.1)
    answer = command()
    thread.join()
    assert not errors, errors
    assert "Error executing" not in answer["content"][0]["text"], answer
    return answer


def held(business: Business, then: Callable[[], None]) -> Callable[[], None]:
    """Offboarding's order: the Business first, a pause, then the rest."""

    def side() -> None:
        with transaction.atomic():
            list(Business.objects.select_for_update().filter(pk=business.pk))
            time.sleep(0.4)
            then()

    return side


def test_a_chat_approval_and_a_revoke_of_its_token() -> None:
    _, secret, change = staged()
    token = AccessToken.objects.get()

    def revoke() -> None:
        # Hold the token's row as the revoke's own UPDATE does, while the approval runs, then revoke. With the old
        # SELECT ... FOR UPDATE this was a deadlock: the approval's Command record needs the token row too.
        with transaction.atomic():
            list(AccessToken.objects.select_for_update(no_key=True).filter(pk=token.pk))
            time.sleep(0.4)
            token.revoke()

    def approve() -> dict[str, Any]:
        answer = ask(
            "tools/call",
            {"name": "approve_change", "arguments": {"change": change}},
            secret,
        )
        if (
            answer.status_code == 401
        ):  # the revoke committed first: refused at the door, as it should be
            return {"content": [{"text": "refused"}]}
        assert answer.status_code == 200, answer.content
        return answer.json()["result"]

    alongside(revoke, approve)
    assert PendingChange.objects.get().decision in ("approved", "cancelled")


def test_a_chat_approval_and_offboarding() -> None:
    business, secret, change = staged()
    token = AccessToken.objects.get()
    alongside(
        held(business, token.revoke),
        lambda: run(secret, "approve_change", change=change),
    )
    assert PendingChange.objects.get().decision in ("approved", "cancelled")


def test_staging_and_offboarding() -> None:
    business, secret, _ = staged()
    token = AccessToken.objects.get()
    alongside(
        held(business, token.revoke),
        lambda: run(secret, "change_business_details", name="Owner's Hair"),
    )
    assert all(c.decision in ("", "cancelled") for c in PendingChange.objects.all())


def test_a_revoke_in_flight_lets_a_command_still_record_itself() -> None:
    """The deadlock VOI-246 removed: a revoke that held its token FOR UPDATE blocked a Command's record (a foreign key to
    the token) while that Command held the change the revoke wanted next. The revoke's own lock must not block the record."""
    staged()
    token = AccessToken.objects.get()
    revoking = threading.Event()

    def revoke_and_wait() -> None:
        with transaction.atomic():
            AccessToken.revoke_all(AccessToken.objects.filter(pk=token.pk))
            revoking.set()
            time.sleep(0.6)

    def record() -> dict[str, Any]:
        assert revoking.wait(2)
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute("SET LOCAL lock_timeout = '200ms'")
            CommandRecord.objects.create(
                token=token, command="approve_change", result="done"
            )
        return {"content": [{"text": "recorded"}]}

    alongside(revoke_and_wait, record)
