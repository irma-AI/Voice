"""Petter's totals page: who may open it, who may change that, and what it adds up (make test-db). No mocks of our own code."""

# pyright: basic
# (django-stubs types model fields for mypy's plugin; strict pyright cannot read them)

from datetime import UTC, datetime
from decimal import Decimal
from io import StringIO
from typing import Any

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, transaction
from django.test import Client
from django.urls import NoReverseMatch, get_resolver, reverse

from portal.accounts.models import Account
from tests.portal.helpers import PASSWORD, business_with_login
from tests.portal.test_recent_calls import a_call
from tests.portal.test_routes import route_names

pytestmark = [pytest.mark.db, pytest.mark.django_db]

EMAIL = "petter.testsson@example.com"  # synthetic


def run_marker(email: str, *, clear: bool = False, execute: bool = False) -> str:
    """Runs the command; with execute it first takes the hash from the dry run, as a reviewer would."""
    out = StringIO()
    call_command("totals_marker", email, clear=clear, target="local", stdout=out)
    shown = out.getvalue()
    if execute:
        digest = shown.split("plan sha256: ")[1].split()[0]
        call_command(
            "totals_marker",
            email,
            clear=clear,
            target="local",
            execute=True,
            approved_hash=digest,
            stdout=StringIO(),
        )
    return shown


def marked(email: str) -> bool:
    return Account.objects.get(email=email).sees_totals


def test_only_a_marked_account_sees_the_page() -> None:
    _, client = business_with_login(EMAIL, "Petter's Business")
    assert client.get("/totals/").status_code == 403
    run_marker(EMAIL, execute=True)
    assert client.get("/totals/").status_code == 200
    run_marker(EMAIL, clear=True, execute=True)
    assert client.get("/totals/").status_code == 403
    assert Client().get("/totals/")["Location"].startswith("/login/")


def test_the_command_changes_nothing_without_the_reviewed_hash_or_for_the_wrong_target() -> (
    None
):
    business_with_login(EMAIL, "Petter's Business")
    run_marker(EMAIL)
    assert not marked(EMAIL)
    with pytest.raises(CommandError, match="plan changed"):
        call_command(
            "totals_marker",
            EMAIL,
            target="local",
            execute=True,
            approved_hash="0" * 64,
        )
    with pytest.raises(CommandError, match="--target production"):
        call_command("totals_marker", EMAIL, target="production")
    with pytest.raises(CommandError, match="no Account"):
        call_command("totals_marker", "nobody@example.com", target="local")
    assert not marked(EMAIL)


def test_the_database_refuses_every_other_way_to_set_or_clear_the_marker() -> None:
    petter, _ = business_with_login(EMAIL, "Petter's Business")
    account = petter.account
    account.sees_totals = True
    with pytest.raises(IntegrityError, match="totals_marker"), transaction.atomic():
        account.save()
    with pytest.raises(IntegrityError, match="totals_marker"), transaction.atomic():
        Account.objects.create(email="other@example.com", sees_totals=True)
    run_marker(EMAIL, execute=True)
    account.refresh_from_db()
    account.sees_totals = False
    with pytest.raises(IntegrityError, match="totals_marker"), transaction.atomic():
        account.save()
    assert marked(EMAIL)
    # Ordinary saves of the account (a login, a password) leave the marker alone and are let through.
    account.set_password("another-long-passphrase")
    account.sees_totals = True
    account.save()


def test_no_page_changes_the_marker() -> None:
    _, _ = business_with_login(EMAIL, "Petter's Business")
    for name in route_names(get_resolver().url_patterns):
        try:
            address = reverse(name)
        except NoReverseMatch:
            try:
                address = reverse(name, args=[1])  # a page of one thing, by its number
            except NoReverseMatch:
                address = reverse(name, kwargs={"uidb64": "x", "token": "y"})
        client = Client()
        assert client.login(email=EMAIL, password=PASSWORD)
        client.get(address)
        client.post(address, {"sees_totals": "on", "email": EMAIL, "name": "x"})
        assert not marked(EMAIL), f"{name} changed the marker"


def test_each_month_is_by_call_start_on_the_portal_clock_and_kinds_stay_apart(
    settings: Any,
) -> None:
    anna, _ = business_with_login("anna.testsson@example.com", "Anna's Salon")
    _, petter = business_with_login(EMAIL, "Petter's Business")
    run_marker(EMAIL, execute=True)
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
    page = petter.get("/totals/").content.decode()
    assert page.count("2026-10") == 1 and "$0.5000" in page[page.index("2026-10") :]


def test_calls_without_a_cost_are_counted_and_add_no_dollars() -> None:
    anna, _ = business_with_login("anna.testsson@example.com", "Anna's Salon")
    _, petter = business_with_login(EMAIL, "Petter's Business")
    run_marker(EMAIL, execute=True)
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
