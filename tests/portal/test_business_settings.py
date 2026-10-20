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
    business, client = business_with_login("anna.testsson@example.com", "Anna's Salon")
    assert ask_core(business.pk).json()["name"] == "Anna's Salon"

    response = client.post(
        "/settings/",
        {
            "name": "Anna's Hair",
            "instructions": "Open mon-fri 8-17. A cut costs 400 kr. Closed in July.",
            "languages": ["sv", "en"],
        },
    )
    assert response["Location"] == "/settings/?saved=1"
    assert "Saved." in client.get(response["Location"]).content.decode()

    told = ask_core(business.pk).json()
    assert told == {
        "name": "Anna's Hair",
        "instructions": "Open mon-fri 8-17. A cut costs 400 kr. Closed in July.",
        "languages": ["sv", "en"],
        "modules": [],
    }
    assert not schema_errors(told)


def test_a_bad_edit_is_refused_and_changes_nothing() -> None:
    business, client = business_with_login("anna.testsson@example.com", "Anna's Salon")
    bad_edits: list[dict[str, Any]] = [
        {"name": "  ", "languages": ["sv"]},  # blank name
        {"name": "Anna", "languages": []},  # no language
        {"name": "Anna", "languages": ["de"]},  # not a known language
        {"name": "Anna", "instructions": "x" * 5001, "languages": ["sv"]},  # too long
    ]
    for bad in bad_edits:
        assert client.post("/settings/", bad).status_code == 200
    assert ask_core(business.pk).json() == Business.objects.get().as_settings()
    assert Business.objects.get().as_settings()["name"] == "Anna's Salon"


def test_a_business_edits_only_its_own_settings() -> None:
    anna, anna_client = business_with_login("anna.testsson@example.com", "Anna's Salon")
    bo, _ = business_with_login("bo.testsson@example.com", "Bo's Garage")
    anna_client.post("/settings/", {"name": "Anna's Hair", "languages": ["sv"]})
    assert ask_core(anna.pk).json()["name"] == "Anna's Hair"
    assert ask_core(bo.pk).json()["name"] == "Bo's Garage"


def test_a_post_of_settings_needs_a_login() -> None:
    assert Client().post("/settings/", {"name": "x"}).status_code == 302


def test_the_settings_address_refuses_a_missing_or_wrong_secret_and_unknown_businesses() -> (
    None
):
    business, _ = business_with_login("anna.testsson@example.com", "Anna's Salon")
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
    business, _ = business_with_login("anna.testsson@example.com", "Anna's Salon")
    assert ask_core(business.pk, "").status_code == 401
    assert ask_core(business.pk, None).status_code == 401


def test_the_settings_address_only_reads() -> None:
    business, _ = business_with_login("anna.testsson@example.com", "Anna's Salon")
    for method in ("post", "put", "delete"):
        response = getattr(Client(), method)(
            f"/api/settings/{business.pk}/",
            headers={"Authorization": f"Bearer {SECRET}"},
        )
        assert response.status_code == 405
    assert Business.objects.get().as_settings()["name"] == "Anna's Salon"


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
    account = Account.objects.create_user("anna.testsson@example.com")
    with (
        pytest.raises(
            IntegrityError, match="business_languages_must_be_one_or_more_known"
        )
        if refused
        else nullcontext(),
        transaction.atomic(),
    ):
        Business.objects.create(account=account, name="A", languages=languages)


def test_the_database_refuses_a_setting_longer_than_the_contract_allows() -> None:
    account = Account.objects.create_user("anna.testsson@example.com")
    with pytest.raises(DataError, match="value too long"), transaction.atomic():
        Business.objects.create(account=account, name="A", instructions="x" * 5001)


def test_the_response_is_plain_json() -> None:
    business, _ = business_with_login("anna.testsson@example.com", "Anna's Salon")
    response = ask_core(business.pk)
    assert response["Content-Type"] == "application/json"
    assert "no-store" in response["Cache-Control"]
    assert json.loads(response.content)["languages"] == ["sv"]
