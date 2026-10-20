# pyright: basic
# (django-stubs types model fields for mypy's plugin; strict pyright cannot read them)
"""Offboarding a Business: the one way its personal data leaves the Portal (make test-db). No mocks of our own code."""

import re
from datetime import UTC, datetime
from decimal import Decimal
from io import StringIO
from typing import Any

import pytest
from django.core import mail
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client

from portal.accounts.models import AccessToken, Account, Business, CallRecord, Module
from tests.portal.helpers import PASSWORD, a_call, business_with_login

pytestmark = [pytest.mark.db, pytest.mark.django_db]

EMAIL = "user-a@example.com"  # synthetic
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 40


def a_business_with_everything() -> Business:
    business, _ = business_with_login(EMAIL, "Owner A's Salon")
    business.instructions = "Owner A cuts hair on Tuesdays."
    business.website_domain = "site-a.example.se"
    business.accent = "#2f6f4f"
    business.privacy_url = "https://site-a.example.se/privacy"
    business.set_logo(PNG)
    business.save()
    Module.objects.create(
        business=business, name="Bookings", url="https://mcp.example.se/"
    )
    AccessToken.make(business, "Owner A's laptop", "read", is_operator=False)
    AccessToken.make(business, "Owner A's old phone", "full", is_operator=False)[
        0
    ].revoke()
    a_call(business, "c0ffee0123456789", datetime(2026, 10, 17, 9, tzinfo=UTC))
    return business


def offboard(email: str = EMAIL, target: str = "local") -> str:
    """The reviewed way: the dry run's hash, then --execute with it. Returns the dry run's output."""
    dry = StringIO()
    call_command("offboard_business", email, target=target, stdout=dry)
    digest = re.search(r"plan sha256: (\w+)", dry.getvalue())
    assert digest, dry.getvalue()
    call_command(
        "offboard_business",
        email,
        target=target,
        execute=True,
        approved_hash=digest.group(1),
        stdout=StringIO(),
    )
    return dry.getvalue()


def test_the_dry_run_changes_nothing_and_execute_needs_the_reviewed_hash_and_target() -> (
    None
):
    business = a_business_with_everything()
    before = list(Business.objects.values()), list(Account.objects.values())
    dry = StringIO()
    call_command("offboard_business", EMAIL, target="local", stdout=dry)
    assert f'"business": "{business.pk}"' in dry.getvalue()
    assert '"name now": "Owner A\'s Salon"' in dry.getvalue()
    assert '"access tokens to revoke": "1"' in dry.getvalue()
    assert '"modules to delete": "1"' in dry.getvalue()
    with pytest.raises(CommandError, match="plan changed"):
        call_command(
            "offboard_business",
            EMAIL,
            target="local",
            execute=True,
            approved_hash="0" * 64,
        )
    with pytest.raises(CommandError, match="--target production"):
        call_command("offboard_business", EMAIL, target="production")
    with pytest.raises(CommandError, match="no Account"):
        call_command("offboard_business", "nobody@example.com", target="local")
    assert (list(Business.objects.values()), list(Account.objects.values())) == before
    assert Module.objects.count() == 1
    assert AccessToken.objects.filter(revoked_at__isnull=True).count() == 1


# Every column of the two rows, each either emptied by offboarding or holding nothing about a person.
# A new column fails the sweep below until it is listed here.
def emptied(business: Business) -> dict[str, dict[str, Any]]:
    return {
        "account": {
            "email": f"deleted-{business.account.pk}@invalid",
            "is_active": False,
            "last_login": None,
        },
        "business": {
            "name": f"Business {business.pk}",
            "instructions": "",
            "website_domain": "",
            "logo": None,
            "logo_key": "",
            "accent": "",
            "privacy_url": "",
            "daily_budget_usd": Decimal("0.00"),  # its call link spends nothing more
        },
    }


NOT_ABOUT_A_PERSON = {
    "account": {"id", "password"},  # password: unusable, checked below
    "business": {"id", "account", "languages", "call_slug"},
}


def test_offboarding_leaves_no_personal_data_and_keeps_the_call_records() -> None:
    business = a_business_with_everything()
    calls_before = list(CallRecord.objects.values())
    offboard()

    business.refresh_from_db()
    account = Account.objects.get(pk=business.account.pk)
    want = emptied(business)
    for kind, row in (("account", account), ("business", business)):
        columns = {f.name for f in type(row)._meta.concrete_fields}
        assert columns == set(want[kind]) | NOT_ABOUT_A_PERSON[kind], (
            f"list the {kind} column in emptied() or NOT_ABOUT_A_PERSON"
        )
        for name, value in want[kind].items():
            stored = getattr(row, name)
            assert (
                bytes(stored) if isinstance(stored, memoryview) else stored
            ) == value, name
    assert not account.has_usable_password()
    assert not Module.objects.exists()
    assert not AccessToken.objects.filter(revoked_at__isnull=True).exists()
    assert [(t.label, t.pk) for t in AccessToken.objects.all()] == [
        (f"Token {t.pk}", t.pk) for t in AccessToken.objects.all()
    ]  # a label may name a person
    assert list(CallRecord.objects.values()) == calls_before


def test_the_call_records_still_add_up_on_the_totals_page(settings: Any) -> None:
    business = a_business_with_everything()
    offboard()
    _, operator = business_with_login("operator@example.com", "Voice")
    settings.SUPER_ADMIN_EMAIL = "operator@example.com"
    page = operator.get("/totals/").content.decode()
    assert f"Business {business.pk}" in page and "Owner A" not in page
    assert "3.1" in page  # the one 184-second call, in minutes


def test_the_tombstone_cannot_log_in_or_get_a_reset_link() -> None:
    business = a_business_with_everything()
    offboard()
    tombstone = f"deleted-{business.account.pk}@invalid"
    for email in (EMAIL, tombstone):
        response = Client().post("/login/", {"username": email, "password": PASSWORD})
        assert response.status_code == 200  # the form again, not a redirect in
    mail.outbox.clear()
    for email in (EMAIL, tombstone):
        Client().post("/password-reset/", {"email": email})
    assert mail.outbox == []
