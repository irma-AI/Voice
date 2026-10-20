"""The operator's Commands: the totals, and an invite that waits for approval (VOI-116, make test-db). No mocks of our own code.

The Commands run on the SDK's worker threads with their own database connection, so these tests commit (transaction=True).
"""

# pyright: basic
# (django-stubs types model fields for mypy's plugin; strict pyright cannot read them)

import html
from datetime import UTC, datetime
from typing import Any

import pytest
from django.core import mail

from portal.accounts import views
from portal.accounts.models import (
    Account,
    Business,
    CommandRecord,
    PendingChange,
    StagedValues,
)
from tests.portal.helpers import a_call, business_with_login
from tests.portal.test_agent_endpoint import a_token, ask, tool_names
from tests.portal.test_pending_changes import decided

pytestmark = [pytest.mark.db, pytest.mark.django_db(transaction=True)]

OPERATOR = "operator@example.com"


@pytest.fixture(autouse=True)
def operator_named(settings: Any) -> None:
    settings.SUPER_ADMIN_EMAIL = OPERATOR


def run(secret: str, command: str, **arguments: Any) -> dict[str, Any]:
    answer = ask("tools/call", {"name": command, "arguments": arguments}, secret)
    assert answer.status_code == 200, answer.content
    return answer.json()["result"]


def text(answer: dict[str, Any]) -> str:
    return answer["content"][0]["text"]


def the_operator() -> tuple[Business, Any]:
    return business_with_login(OPERATOR, "Voice")


def unknown(secret: str, command: str, **arguments: Any) -> bool:
    answer = run(secret, command, **arguments)
    return bool(answer.get("isError")) and text(answer) == f"Unknown tool: {command}"


def test_only_the_operators_tokens_see_and_run_the_operator_commands() -> None:
    operator, _ = the_operator()
    business, _ = business_with_login("user-a@example.com", "Owner A's Salon")
    for scope in ("read", "full"):
        secret = a_token(business, scope, operator=False)
        listed = tool_names(ask("tools/list", secret=secret))
        assert "list_totals" not in listed and "invite_business" not in listed
        assert unknown(secret, "list_totals")
        assert unknown(secret, "invite_business", name="X", email="x@example.com")
    read = a_token(operator, "read", operator=True)
    assert "list_totals" in tool_names(ask("tools/list", secret=read))
    assert "invite_business" not in tool_names(ask("tools/list", secret=read))
    assert unknown(read, "invite_business", name="X", email="x@example.com")
    full = a_token(operator, "full", operator=True)
    assert {"list_totals", "invite_business"} <= set(
        tool_names(ask("tools/list", secret=full))
    )
    assert not PendingChange.objects.exists()


def test_with_no_operator_named_no_token_is_an_operators(settings: Any) -> None:
    operator, _ = the_operator()
    secret = a_token(operator, "full", operator=True)
    settings.SUPER_ADMIN_EMAIL = ""
    assert "list_totals" not in tool_names(ask("tools/list", secret=secret))
    assert unknown(secret, "list_totals")
    assert CommandRecord.objects.get().result == "refused"


def test_a_token_marked_operator_for_another_account_is_not_one() -> None:
    business, _ = business_with_login("user-a@example.com", "Owner A's Salon")
    secret = a_token(business, "full", operator=True)  # the setting names someone else
    assert unknown(secret, "list_totals")


def test_the_totals_are_the_pages_per_month_business_and_kind() -> None:
    operator, client = the_operator()
    business, _ = business_with_login("user-a@example.com", "Owner A's Salon")
    a_call(business, "call-000000001", datetime(2026, 9, 3, 9, tzinfo=UTC))
    a_call(business, "call-000000002", datetime(2026, 9, 4, 9, tzinfo=UTC), kind="test")
    totals = run(a_token(operator, "read", operator=True), "list_totals")[
        "structuredContent"
    ]["result"]
    assert totals == [
        {
            "month": "2026-09",
            "business": "Owner A's Salon",
            "kinds": {
                "test": {
                    "calls": 1,
                    "minutes": "3.1",
                    "dollars": "0.0123",
                    "unpriced": 0,
                },
                "call_link": {
                    "calls": 1,
                    "minutes": "3.1",
                    "dollars": "0.0123",
                    "unpriced": 0,
                },
                "demo": {
                    "calls": 0,
                    "minutes": "0.0",
                    "dollars": "0.0000",
                    "unpriced": 0,
                },
            },
        }
    ]
    page = client.get("/totals/").content.decode()
    assert "2026-09" in page and "Owner A&#x27;s Salon" in page


def test_an_invite_waits_for_the_operators_approval_then_goes_out_once() -> None:
    operator, client = the_operator()
    secret = a_token(operator, "full", operator=True)
    answer = run(secret, "invite_business", name="New Salon", email="New@Example.com")
    staged = answer["structuredContent"]
    assert (
        staged["staged"] is True
        and staged["preview"] == "Invite “New Salon” at new@example.com"
    )
    assert (
        not Account.objects.filter(email="new@example.com").exists()
        and mail.outbox == []
    )
    assert CommandRecord.objects.get().result == "staged"
    change = PendingChange.objects.get()
    assert "new@example.com" not in str(change.target)
    assert views.OUTCOMES["applied"] in decided(client, change, "approve")
    assert Business.objects.get(account__email="new@example.com").name == "New Salon"
    assert len(mail.outbox) == 1 and not StagedValues.objects.exists()


@pytest.mark.parametrize(
    ("name", "email"),
    [
        ("New Salon", "not an email"),
        ("  ", "new@example.com"),
        ("A\nB", "new@example.com"),
        ("Taken", "user-a@example.com"),
    ],
)
def test_an_invite_the_management_command_would_refuse_is_refused_plainly(
    name: str, email: str
) -> None:
    operator, _ = the_operator()
    business_with_login("user-a@example.com", "Owner A's Salon")
    answer = run(
        a_token(operator, "full", operator=True),
        "invite_business",
        name=name,
        email=email,
    )
    assert answer.get("isError") and not PendingChange.objects.exists()
    assert "Traceback" not in text(answer)


def test_an_invite_that_can_no_longer_go_out_keeps_waiting_and_creates_nothing(
    settings: Any,
) -> None:
    operator, client = the_operator()
    run(
        a_token(operator, "full", operator=True),
        "invite_business",
        name="New Salon",
        email="new@example.com",
    )
    business_with_login(
        "new@example.com", "Someone Else"
    )  # the email got an account meanwhile
    change = PendingChange.objects.get()
    page = html.unescape(decided(client, change, "approve"))
    assert views.OUTCOMES["invite_refused"] in page
    assert (
        Business.objects.filter(account__email="new@example.com").get().name
        == "Someone Else"
    )
    assert PendingChange.objects.get().decision == ""
    assert mail.outbox == []


def test_an_invite_is_not_sent_once_its_asker_is_no_longer_the_operator(
    settings: Any,
) -> None:
    operator, client = the_operator()
    run(
        a_token(operator, "full", operator=True),
        "invite_business",
        name="New Salon",
        email="new@example.com",
    )
    settings.SUPER_ADMIN_EMAIL = "someone-else@example.com"
    page = html.unescape(decided(client, PendingChange.objects.get(), "approve"))
    assert views.OUTCOMES["not_operator"] in page
    assert (
        not Account.objects.filter(email="new@example.com").exists()
        and mail.outbox == []
    )


def test_an_invite_whose_mail_cannot_go_out_creates_nothing_and_keeps_waiting(
    settings: Any,
) -> None:
    operator, client = the_operator()
    run(
        a_token(operator, "full", operator=True),
        "invite_business",
        name="New Salon",
        email="new@example.com",
    )
    # A real mail connection to a port nobody listens on.
    settings.MAILERS = {
        "default": {
            "BACKEND": "django.core.mail.backends.smtp.EmailBackend",
            "OPTIONS": {"host": "127.0.0.1", "port": 1},
        }
    }
    page = html.unescape(decided(client, PendingChange.objects.get(), "approve"))
    assert views.OUTCOMES["invite_refused"] in page
    assert not Account.objects.filter(email="new@example.com").exists()
    assert PendingChange.objects.get().decision == ""
