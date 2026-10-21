"""A logged-in Business presses the test call button and is sent to the core with a ticket for itself only (make test-db).

The ticket is signed here and checked by the core's own code (voice/ticket.py): neither service imports the other,
so this test is where the two formats are held together. A failure names the side to edit.
"""

import time
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from django.test import Client

from portal.accounts.models import Business
from portal.accounts.ticket import TTL_SECONDS
from tests.portal.helpers import business_with_login
from voice.settings import load_settings
from voice.ticket import Ticket, read_ticket

pytestmark = [pytest.mark.db, pytest.mark.django_db]

SECRET = "a-secret-for-tests"


@pytest.fixture(autouse=True)
def core(settings: Any) -> None:
    settings.CORE_SECRET = SECRET
    settings.CORE_URL = "https://voice.example.se/"


def ticket_in(location: str) -> str:
    parts = urlsplit(location)
    assert (parts.scheme, parts.netloc, parts.path) == (
        "https",
        "voice.example.se",
        "/",
    )
    return parse_qs(parts.query)["ticket"][0]


def test_the_button_sends_a_business_to_the_core_with_a_ticket_for_itself() -> None:
    business, client = business_with_login("user-a@example.com", "Owner A's Salon")
    other, _ = business_with_login()

    # Naming another Business in the request changes nothing: the ticket follows the session.
    response = client.post(
        "/test-call/", {"business": other.pk, "business_id": other.pk}
    )

    assert response.status_code == 302
    ticket = ticket_in(response["Location"])
    drift = "portal/accounts/ticket.py and voice/ticket.py disagree: edit the one that changed"
    assert read_ticket(ticket, SECRET) == Ticket(business.pk, "test", ""), (
        drift
    )  # a test call carries no domain: its page cannot be framed
    assert business.pk != other.pk
    assert read_ticket(ticket, SECRET, time.time() + TTL_SECONDS + 5) is None, drift
    assert read_ticket(ticket, "another-secret") is None, drift


def test_a_visitor_gets_no_ticket_and_a_page_visit_starts_nothing() -> None:
    business_with_login("user-a@example.com", "Owner A's Salon")

    response = Client().post("/test-call/")
    assert response.status_code == 302 and response["Location"].startswith("/login/")
    assert "ticket" not in response["Location"]

    _, client = business_with_login()
    # A link or an image cannot start a call: it goes back to the dashboard, where a login after an ended session lands.
    assert client.get("/test-call/")["Location"] == "/dashboard/"


def test_a_cross_site_post_is_refused_by_the_csrf_check() -> None:
    _, client = business_with_login("user-a@example.com", "Owner A's Salon")
    strict = Client(enforce_csrf_checks=True)
    strict.cookies = client.cookies
    assert strict.post("/test-call/").status_code == 403


def test_the_dashboard_offers_the_button_to_a_business() -> None:
    _, client = business_with_login("user-a@example.com", "Owner A's Salon")
    page = client.get("/dashboard/").content.decode()
    assert 'action="/test-call/"' in page and "Test call" in page


def test_the_core_reads_the_ticketed_businesss_settings_from_the_real_portal(
    live_server: Any,
) -> None:
    business_a, client = business_with_login("user-a@example.com", "Owner A's Salon")
    Business.objects.filter(pk=business_a.pk).update(instructions="Open 8-17.")
    business_with_login()

    ticket = ticket_in(client.post("/test-call/")["Location"])
    named = read_ticket(ticket, SECRET)
    assert named is not None
    core_env = {"SETTINGS_URL": live_server.url, "CORE_SECRET": SECRET}
    got = load_settings(core_env, str(named.business))
    assert (got.name, got.instructions) == ("Owner A's Salon", "Open 8-17.")


def test_a_portal_with_no_secret_hands_out_no_ticket(settings: Any) -> None:
    settings.CORE_SECRET = ""
    _, client = business_with_login("user-a@example.com", "Owner A's Salon")
    response = client.post("/test-call/")
    assert response.status_code == 503 and "Location" not in response
