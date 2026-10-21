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
from portal.accounts.views import BUDGET_SPENT_REFUSAL
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
    business, client = business_with_login()
    secret = a_token(business, "read")
    refused = run(secret, "get_call_button")
    assert refused.get("isError") and "website" in text(refused)
    Business.objects.filter(pk=business.pk).update(website_domain="example.se")
    tag = run(secret, "get_call_button")["structuredContent"]["script"]
    assert tag.startswith("<script") and business.call_slug in tag
    assert tag in html.unescape(client.get("/dashboard/").content.decode())


def test_the_test_call_link_is_a_test_call_counted_toward_the_budget() -> None:
    business, client = business_with_login()
    secret = a_token(business, "full")
    link = run(secret, "get_test_call_link")["structuredContent"]["link"]
    button = client.post("/test-call/")["Location"]
    # The button's own call page and limits; only the kind differs, so the core and the budget can tell them apart.
    assert link.split("?")[0] == button.split("?")[0]
    assert read_ticket(ticket_in(link), SECRET) == Ticket(business.pk, "agent_test", "")
    assert CommandRecord.objects.get().result == "done"
    assert "ticket" not in str(list(CommandRecord.objects.values()))
    Business.objects.filter(pk=business.pk).update(daily_budget_usd=0)
    refused = run(secret, "get_test_call_link")
    assert refused.get("isError") and text(refused) == BUDGET_SPENT_REFUSAL
    assert (
        client.post("/test-call/").status_code == 302
    )  # the button's own test call stays exempt


def test_a_read_only_token_gets_no_test_call_link() -> None:
    business, _ = business_with_login()
    answer = run(a_token(business, "read"), "get_test_call_link")
    assert answer.get("isError") and text(answer) == "Unknown tool: get_test_call_link"


def test_no_link_while_calls_are_not_set_up(settings: Any) -> None:
    settings.CORE_SECRET = ""
    business, _ = business_with_login()
    answer = run(a_token(business, "full"), "get_test_call_link")
    assert answer.get("isError") and "ticket" not in text(answer)
