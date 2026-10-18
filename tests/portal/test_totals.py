"""Petter's totals page: who may open it and what it adds up (make test-db). No mocks of our own code."""

# pyright: basic
# (django-stubs types model fields for mypy's plugin; strict pyright cannot read them)

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from django.test import Client

from tests.portal.helpers import business_with_login
from tests.portal.test_recent_calls import a_call

pytestmark = [pytest.mark.db, pytest.mark.django_db]

EMAIL = "petter.testsson@example.com"  # synthetic


def test_only_the_account_named_in_the_setting_sees_the_page(settings: Any) -> None:
    _, client = business_with_login(EMAIL, "Petter's Business")
    _, other = business_with_login("anna.testsson@example.com", "Anna's Salon")
    settings.SUPER_ADMIN_EMAIL = ""  # unset: nobody, not even the right account
    assert client.get("/totals/").status_code == 403
    assert "Totals for every Business" not in client.get("/dashboard/").content.decode()
    settings.SUPER_ADMIN_EMAIL = EMAIL
    assert client.get("/totals/").status_code == 200
    assert "Totals for every Business" in client.get("/dashboard/").content.decode()
    assert other.get("/totals/").status_code == 403
    assert Client().get("/totals/")["Location"].startswith("/login/")


def test_each_month_is_by_call_start_on_the_portal_clock_and_kinds_stay_apart(
    settings: Any,
) -> None:
    settings.SUPER_ADMIN_EMAIL = EMAIL
    anna, _ = business_with_login("anna.testsson@example.com", "Anna's Salon")
    _, petter = business_with_login(EMAIL, "Petter's Business")
    settings.TIME_ZONE = "Europe/Stockholm"  # CET from 2026-10-25: one hour ahead
    # 23:30 UTC on 31 October is 00:30 on 1 November in Stockholm; 21:30 UTC is still October.
    a_call(anna, "late-oct-000001", datetime(2026, 10, 31, 21, 30, tzinfo=UTC))
    a_call(
        anna,
        "new-month-00001",
        datetime(2026, 10, 31, 23, 30, tzinfo=UTC),
        kind="test",
        length_seconds=90,
        cost_usd="0.5",
    )
    a_call(
        anna,
        "unpriced-00000001",
        datetime(2026, 11, 2, 9, 0, tzinfo=UTC),
        cost_usd=None,
        price_date=None,
        cost_reason="price_unavailable",
    )

    page = petter.get("/totals/").content.decode()
    assert page.index("2026-11") < page.index("2026-10")  # newest month first
    october = page[page.index("2026-10") :]
    assert "$0.0123" in october  # the 21:30 call, priced
    november = page[page.index("2026-11") : page.index("2026-10")]
    assert "$0.5000" in november and "1.5" in november  # the 23:30 test call lands here
    assert "Test calls" in page and "Call links" in page

    settings.TIME_ZONE = "UTC"  # on the UTC clock the 23:30 call is October
    rows = petter.get("/totals/").context["rows"]
    october = [cells for month, _, cells in rows if month == "2026-10"]
    assert len(october) == 1 and "0.5000" in [c[2] for c in october[0]]


def test_calls_without_a_cost_are_counted_and_add_no_dollars(settings: Any) -> None:
    settings.SUPER_ADMIN_EMAIL = EMAIL
    anna, _ = business_with_login("anna.testsson@example.com", "Anna's Salon")
    _, petter = business_with_login(EMAIL, "Petter's Business")
    when = datetime(2026, 10, 17, 5, 0, tzinfo=UTC)
    a_call(anna, "priced-000000001", when, cost_usd="0.25")
    a_call(
        anna,
        "unpriced-00000001",
        when,
        cost_usd=None,
        price_date=None,
        cost_reason="price_unavailable",
    )
    row = petter.get("/totals/").context["rows"][0]
    assert row[:2] == ("2026-10", "Anna's Salon")
    test_cells, link_cells = row[2]
    assert test_cells == (0, "0.0", "0.0000", 0)
    assert link_cells == (2, "6.1", "0.2500", 1)  # two 184 s calls, one with no cost
    assert Decimal(link_cells[2]) == Decimal("0.25")


def test_the_table_scrolls_by_keyboard_and_says_what_it_is(settings: Any) -> None:
    settings.SUPER_ADMIN_EMAIL = EMAIL
    _, client = business_with_login(EMAIL, "Petter's Business")
    page = client.get("/totals/").content.decode()
    assert 'role="region"' in page and 'tabindex="0"' in page


def test_phones_get_every_figure_without_the_wide_table(settings: Any) -> None:
    """Below the md breakpoint the wide table is hidden; each month and Business is a block of its own with the same figures."""
    settings.SUPER_ADMIN_EMAIL = EMAIL
    anna, _ = business_with_login("anna.testsson@example.com", "Anna's Salon")
    _, petter = business_with_login(EMAIL, "Petter's Business")
    a_call(
        anna,
        "priced-000000001",
        datetime(2026, 10, 17, 5, 0, tzinfo=UTC),
        cost_usd="0.25",
    )
    page = petter.get("/totals/").content.decode()
    phone = page[
        page.index('class="mt-8 border-b border-granite md:hidden"') : page.index(
            "</ul>"
        )
    ]
    wide = page[page.index('role="region"') :]
    assert "hidden overflow-x-auto md:block" in page
    for part in (phone, wide):
        for figure in (
            "2026-10",
            "Anna&#x27;s Salon",
            "Test calls",
            "Call links",
            "3.1",
            "$0.2500",
            "$0.0000",
        ):
            assert figure in part, (figure, part[:80])
