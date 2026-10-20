"""A Business edits its settings in the Portal and the core reads them from the settings address (make test-db). No mocks of our own code."""

import json
from contextlib import nullcontext
from typing import Any

import pytest
from django.db import DataError, IntegrityError, transaction
from django.test import Client

from portal.accounts.models import Account, Business
from tests.portal.contract import schema_errors
from tests.portal.helpers import SECRET, ask_core, business_with_login

pytestmark = [pytest.mark.db, pytest.mark.django_db]


@pytest.fixture(autouse=True)
def core_secret(settings: Any) -> None:
    settings.CORE_SECRET = SECRET


def test_editing_in_the_portal_changes_what_the_core_is_told() -> None:
    business, client = business_with_login("user-a@example.com", "Owner A's Salon")
    assert ask_core(business.pk).json()["name"] == "Owner A's Salon"

    response = client.post(
        "/settings/",
        {
            "name": "Owner A's Hair",
            "instructions": "Open mon-fri 8-17. A cut costs 400 kr. Closed in July.",
            "languages": ["sv", "en"],
        },
    )
    assert response["Location"] == "/settings/?saved=1"
    assert "Saved." in client.get(response["Location"]).content.decode()

    told = ask_core(business.pk).json()
    assert told == {
        "name": "Owner A's Hair",
        "instructions": "Open mon-fri 8-17. A cut costs 400 kr. Closed in July.",
        "languages": ["sv", "en"],
        "modules": [],
    }
    assert not schema_errors(told)


def test_a_bad_edit_is_refused_and_changes_nothing() -> None:
    business, client = business_with_login("user-a@example.com", "Owner A's Salon")
    bad_edits: list[dict[str, Any]] = [
        {"name": "  ", "languages": ["sv"]},  # blank name
        {"name": "Owner A", "languages": []},  # no language
        {"name": "Owner A", "languages": ["de"]},  # not a known language
        {
            "name": "Owner A",
            "instructions": "x" * 5001,
            "languages": ["sv"],
        },  # too long
    ]
    for bad in bad_edits:
        assert client.post("/settings/", bad).status_code == 200
    assert ask_core(business.pk).json() == Business.objects.get().as_settings()
    assert Business.objects.get().as_settings()["name"] == "Owner A's Salon"


def test_a_business_edits_only_its_own_settings() -> None:
    business_a, client_a = business_with_login("user-a@example.com", "Owner A's Salon")
    business_b, _ = business_with_login("user-b@example.com", "Owner B's Garage")
    client_a.post("/settings/", {"name": "Owner A's Hair", "languages": ["sv"]})
    assert ask_core(business_a.pk).json()["name"] == "Owner A's Hair"
    assert ask_core(business_b.pk).json()["name"] == "Owner B's Garage"


def test_a_post_of_settings_needs_a_login() -> None:
    assert Client().post("/settings/", {"name": "x"}).status_code == 302


def test_the_settings_address_refuses_a_missing_or_wrong_secret_and_unknown_businesses() -> (
    None
):
    business, _ = business_with_login("user-a@example.com", "Owner A's Salon")
    for secret in (None, "", "wrong", SECRET + "x"):
        assert ask_core(business.pk, secret).status_code == 401
    bare = Client().get(
        f"/api/settings/{business.pk}/", headers={"Authorization": SECRET}
    )
    assert bare.status_code == 401  # the right secret without the Bearer scheme
    assert ask_core(business.pk + 1000).status_code == 404
    # A wrong secret is refused before the lookup, so it cannot tell which Businesses exist.
    assert ask_core(business.pk + 1000, "wrong").status_code == 401
    assert ask_core(business.pk).status_code == 200


def test_the_settings_address_refuses_everyone_when_no_secret_is_set(
    settings: Any,
) -> None:
    settings.CORE_SECRET = ""
    business, _ = business_with_login("user-a@example.com", "Owner A's Salon")
    assert ask_core(business.pk, "").status_code == 401
    assert ask_core(business.pk, None).status_code == 401


def test_the_settings_address_only_reads() -> None:
    business, _ = business_with_login("user-a@example.com", "Owner A's Salon")
    for method in ("post", "put", "delete"):
        response = getattr(Client(), method)(
            f"/api/settings/{business.pk}/",
            headers={"Authorization": f"Bearer {SECRET}"},
        )
        assert response.status_code == 405
    assert Business.objects.get().as_settings()["name"] == "Owner A's Salon"


# What must never break is refused by the database itself, whoever writes.


@pytest.mark.parametrize(
    ("languages", "refused"),
    [
        (["sv"], False),
        (["en", "sv"], False),
        ([], True),
        (["de"], True),
        (["sv", "de"], True),
    ],
)
def test_the_database_refuses_no_language_or_an_unknown_one(
    languages: list[str], refused: bool
) -> None:
    account = Account.objects.create_user("user-a@example.com")
    with (
        pytest.raises(
            IntegrityError, match="business_languages_must_be_one_or_more_known"
        )
        if refused
        else nullcontext(),
        transaction.atomic(),
    ):
        Business.objects.create(account=account, name="A", languages=languages)


def test_every_business_greets_in_english_until_it_picks_swedish_and_the_database_refuses_another() -> (
    None
):
    """VOI-255: English by default (Petter, 2026-10-20), Swedish when picked on the settings page; nothing else is stored."""
    business, client = business_with_login("user-a@example.com", "Owner A's Salon")
    assert (
        business.greeting_language == "en"  # pyright: ignore[reportUnknownMemberType]
        and "greeting" not in ask_core(business.pk).json()
    )
    edit = {"name": "Owner A's Salon", "languages": ["sv", "en"]}
    client.post("/settings/", {**edit, "greeting_language": "sv"})
    told = ask_core(business.pk).json()
    assert told["greeting"] == "sv" and not schema_errors(told)
    client.post("/settings/", edit)  # a request without the field keeps it
    assert ask_core(business.pk).json()["greeting"] == "sv"
    refused = client.post("/settings/", {**edit, "greeting_language": "de"})
    assert (
        refused.status_code == 200 and ask_core(business.pk).json()["greeting"] == "sv"
    )
    with (
        pytest.raises(IntegrityError, match="business_greeting_language_must_be_known"),
        transaction.atomic(),
    ):
        Business.objects.filter(pk=business.pk).update(greeting_language="de")


def test_the_database_refuses_a_setting_longer_than_the_contract_allows() -> None:
    account = Account.objects.create_user("user-a@example.com")
    with pytest.raises(DataError, match="value too long"), transaction.atomic():
        Business.objects.create(account=account, name="A", instructions="x" * 5001)


def test_the_response_is_plain_json() -> None:
    business, _ = business_with_login("user-a@example.com", "Owner A's Salon")
    response = ask_core(business.pk)
    assert response["Content-Type"] == "application/json"
    assert "no-store" in response["Cache-Control"]
    assert json.loads(response.content)["languages"] == ["sv"]
