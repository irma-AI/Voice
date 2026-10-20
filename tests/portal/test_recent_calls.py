"""A Business sees its own recent calls on the Portal's clock, with no money (make test-db). No mocks of our own code."""

# pyright: basic
# (django-stubs types model fields for mypy's plugin; strict pyright cannot read them)

from datetime import UTC, datetime
from typing import Any

import pytest
from django.test import Client

from portal.accounts.models import Account, CallRecord
from tests.portal.helpers import a_call, business_with_login

pytestmark = [pytest.mark.db, pytest.mark.django_db]


def shown(client: Client) -> str:
    response = client.get("/calls/")
    assert response.status_code == 200
    return response.content.decode()


def test_a_business_sees_only_its_own_calls_newest_first_with_kind_and_length() -> None:
    business_a, client = business_with_login("user-a@example.com", "Owner A's Salon")
    business_b, _ = business_with_login("user-b@example.com", "Owner B's Bikes")
    a_call(business_a, "older-call-0001", datetime(2026, 10, 17, 5, 0, tzinfo=UTC))
    a_call(
        business_a,
        "newer-call-0002",
        datetime(2026, 10, 17, 6, 30, tzinfo=UTC),
        kind="test",
        length_seconds=65,
    )
    a_call(business_b, "b-call-00000003", datetime(2026, 10, 17, 7, 0, tzinfo=UTC))

    page = shown(client)
    assert page.index("06:30") < page.index("05:00")  # newest first
    assert "07:00" not in page  # Owner B's call
    assert "Test call" in page and "Call link" in page
    assert "1:05" in page and "3:04" in page  # lengths as minutes:seconds


def test_the_page_shows_no_money_and_no_call_id() -> None:
    business_a, client = business_with_login("user-a@example.com", "Owner A's Salon")
    a_call(business_a, "secret-id-000001", datetime(2026, 10, 17, 5, 0, tzinfo=UTC))
    page = shown(client)
    assert "0.01234567" not in page and "0.0123" not in page
    assert "$" not in page and "secret-id-000001" not in page


def test_a_business_with_no_calls_is_told_so() -> None:
    _, client = business_with_login("user-a@example.com", "Owner A's Salon")
    assert "No calls yet" in shown(client)


def test_times_follow_the_portal_time_zone_and_what_is_stored_stays_utc(
    settings: Any,
) -> None:
    business_a, client = business_with_login("user-a@example.com", "Owner A's Salon")
    a_call(business_a, "tz-call-00000001", datetime(2026, 10, 17, 5, 0, tzinfo=UTC))

    settings.TIME_ZONE = "UTC"
    page = shown(client)
    assert "05:00" in page and "UTC" in page

    settings.TIME_ZONE = "Europe/Stockholm"  # CEST in October, two hours ahead
    page = shown(client)
    assert "07:00" in page and "Europe/Stockholm" in page and "05:00" not in page

    assert (
        CallRecord.objects.get().started_at.isoformat() == "2026-10-17T05:00:00+00:00"
    )


def test_a_visitor_and_a_login_without_a_business_get_nothing_of_anyones() -> None:
    business_a, _ = business_with_login("user-a@example.com", "Owner A's Salon")
    a_call(business_a, "a-call-00000001", datetime(2026, 10, 17, 5, 0, tzinfo=UTC))

    account = Account.objects.create_user("nobody@example.com", "x" * 20)
    client = Client()
    client.force_login(account)
    page = shown(client)
    assert "05:00" not in page and "No calls yet" in page


def test_every_logged_in_page_links_to_the_others_and_marks_the_current_one() -> None:
    _, client = business_with_login("user-a@example.com", "Owner A's Salon")
    page = shown(client)
    for href in ('href="/settings/"', 'href="/modules/"', 'href="/calls/"'):
        assert href in page, href
    assert page.count('aria-current="page"') == 1
    assert 'aria-label="Pages"' not in Client().get("/login/").content.decode()
