"""A Business's assistant fetches its Call button script and asks for a Test call link (VOI-115, make test-db). No mocks of our own code.

The link carries the same ticket as the dashboard's test call button, checked by the core's own code (voice/ticket.py), so the
core's limits for a test call (its length, one call per Business) apply unchanged. Commands run on the SDK's worker threads with
their own database connection, so these tests commit (transaction=True).
"""

# pyright: basic
# (django-stubs types model fields for mypy's plugin; strict pyright cannot read them)

import html
from typing import Any

import pytest

from portal.accounts.models import Business, CommandRecord
from tests.portal.helpers import business_with_login
from tests.portal.test_agent_endpoint import a_token, ask
from tests.portal.test_test_call import SECRET, core, ticket_in  # noqa: F401  (core: the autouse fixture)
from voice.ticket import Ticket, read_ticket

pytestmark = [pytest.mark.db, pytest.mark.django_db(transaction=True)]


def run(secret: str, command: str, **arguments: Any) -> dict[str, Any]:
    answer = ask("tools/call", {"name": command, "arguments": arguments}, secret)
    assert answer.status_code == 200, answer.content
    return answer.json()["result"]


def text(answer: dict[str, Any]) -> str:
    return answer["content"][0]["text"]


def test_the_script_is_the_dashboards_tag_once_a_website_is_saved() -> None:
    business, client = business_with_login("user-a@example.com", "Owner A's Salon")
    secret = a_token(business, "read")
    refused = run(secret, "get_call_button")
    assert refused.get("isError") and "website" in text(refused)
    Business.objects.filter(pk=business.pk).update(website_domain="example.se")
    tag = run(secret, "get_call_button")["structuredContent"]["script"]
    assert tag.startswith("<script") and business.call_slug in tag
    assert tag in html.unescape(client.get("/dashboard/").content.decode())


def test_the_test_call_link_carries_the_buttons_own_ticket_for_the_tokens_business() -> (
    None
):
    business, client = business_with_login("user-a@example.com", "Owner A's Salon")
    other, _ = business_with_login("user-b@example.com", "Owner B's Bikes")
    link = run(a_token(business, "full"), "get_test_call_link")["structuredContent"][
        "link"
    ]
    button = client.post("/test-call/")["Location"]
    assert read_ticket(ticket_in(link), SECRET) == read_ticket(
        ticket_in(button), SECRET
    )
    assert read_ticket(ticket_in(link), SECRET) == Ticket(business.pk, "test", "")
    assert other.pk != business.pk
    assert CommandRecord.objects.get().result == "done"
    assert "ticket" not in str(list(CommandRecord.objects.values()))


def test_a_read_only_token_gets_no_test_call_link() -> None:
    business, _ = business_with_login("user-a@example.com", "Owner A's Salon")
    answer = run(a_token(business, "read"), "get_test_call_link")
    assert answer.get("isError") and text(answer) == "Unknown tool: get_test_call_link"


def test_no_link_while_calls_are_not_set_up(settings: Any) -> None:
    settings.CORE_SECRET = ""
    business, _ = business_with_login("user-a@example.com", "Owner A's Salon")
    answer = run(a_token(business, "full"), "get_test_call_link")
    assert answer.get("isError") and "ticket" not in text(answer)
