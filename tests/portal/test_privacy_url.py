# pyright: basic
# (django-stubs types model fields for mypy's plugin; strict pyright cannot read them)
"""A Business saves the address of its own privacy notice in its settings; the core is told it and the call page links it (make test-db). https only."""

from typing import Any

import pytest
from django.db import IntegrityError, transaction
from django.test import Client

from portal.accounts.models import Business
from tests.portal.contract import schema_errors
from tests.portal.helpers import business_with_login, told_to_core

pytestmark = [pytest.mark.db, pytest.mark.django_db]

NOTICE = "https://www.example.se/integritet"


def save(client: Client, url: str) -> Any:
    return client.post(
        "/settings/", {"name": "Owner A", "languages": ["sv"], "privacy_url": url}
    )


def saved_url() -> str:
    return Business.objects.get().privacy_url


def test_the_address_is_saved_and_told_to_the_core(settings: Any) -> None:
    business, client = business_with_login("user-a@example.com", "Owner A's Salon")
    assert save(client, NOTICE)["Location"] == "/settings/?saved=1"
    assert saved_url() == NOTICE

    told = told_to_core(business, settings)
    assert told["privacy_url"] == NOTICE
    assert not schema_errors(told)


def test_an_address_without_a_scheme_is_taken_as_https() -> None:
    _, client = business_with_login("user-a@example.com", "Owner A's Salon")
    save(client, "www.example.se/integritet")
    assert saved_url() == "https://www.example.se/integritet"


@pytest.mark.parametrize(
    "typed",
    [
        "http://www.example.se/integritet",
        "ftp://example.se/x",
        "javascript:alert(1)",
        "not an address",
        "https://example.se/privacy policy",
    ],
)
def test_something_that_is_not_an_https_address_is_refused_and_changes_nothing(
    typed: str,
) -> None:
    _, client = business_with_login("user-a@example.com", "Owner A's Salon")
    save(client, NOTICE)

    response = save(client, typed)

    assert response.status_code == 200
    assert "Nothing was saved" in response.content.decode()
    assert saved_url() == NOTICE


def test_an_empty_value_clears_the_address_and_the_core_is_told_none(
    settings: Any,
) -> None:
    business, client = business_with_login("user-a@example.com", "Owner A's Salon")
    save(client, NOTICE)
    save(client, "  ")
    assert saved_url() == ""
    told = told_to_core(business, settings)
    assert "privacy_url" not in told and not schema_errors(told)


def test_the_settings_page_shows_the_saved_address() -> None:
    _, client = business_with_login("user-a@example.com", "Owner A's Salon")
    save(client, NOTICE)
    assert f'value="{NOTICE}"' in client.get("/settings/").content.decode()


@pytest.mark.parametrize(
    "bad",
    [
        "http://example.se/integritet",  # not https
        "example.se/integritet",  # no scheme
        "https://",  # nothing after the scheme
        "https://example.se/privacy policy",  # a space
        "https://example.se/x\r\nSet-Cookie: x=1",  # a header line
        "javascript:alert(1)",
    ],
)
def test_the_database_refuses_a_stored_address_that_is_not_https(bad: str) -> None:
    business, _ = business_with_login("user-a@example.com", "Owner A's Salon")
    # The savepoint keeps the test's own transaction usable after Postgres refuses the write.
    with (
        pytest.raises(
            IntegrityError,
            match="business_privacy_url_must_be_empty_or_an_https_address",
        ),
        transaction.atomic(),
    ):
        Business.objects.filter(pk=business.pk).update(privacy_url=bad)
