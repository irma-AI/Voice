# pyright: basic
# (django-stubs types model fields for mypy's plugin; strict pyright cannot read them)
"""A Business saves the domain of its own website in its settings and sees it on its dashboard (make test-db). The domain is Portal-only."""

from typing import Any

import pytest
from django.db import IntegrityError, transaction
from django.test import Client

from portal.accounts.models import Business
from tests.portal.contract import schema_errors
from tests.portal.helpers import business_with_login, told_to_core

pytestmark = [pytest.mark.db, pytest.mark.django_db]


def save(client: Client, website: str) -> Any:
    return client.post(
        "/settings/",
        {"name": "Owner A", "languages": ["sv"], "website_domain": website},
    )


def saved_domain() -> str:
    return Business.objects.get().website_domain


@pytest.mark.parametrize(
    ("typed", "stored"),
    [
        ("https://www.Shop.Example.SE:8443/x", "example.se"),
        ("example.se", "example.se"),
        ("www.example.se", "example.se"),
        ("  EXAMPLE.se.  ", "example.se"),
        ("shop.example.co.uk", "example.co.uk"),
        ("site-a.github.io", "site-a.github.io"),  # the private section counts
        ("site-b.github.io", "site-b.github.io"),
        ("https://www.bücher.se/", "xn--bcher-kva.se"),
        ("faß.de", "xn--fa-hia.de"),  # what a browser sends, not IDNA 2003's fass.de
    ],
)
def test_what_is_typed_is_saved_as_the_registrable_domain(
    typed: str, stored: str
) -> None:
    _, client = business_with_login()
    assert save(client, typed)["Location"] == "/settings/?saved=1"
    assert saved_domain() == stored


@pytest.mark.parametrize(
    "typed",
    [
        "10.0.0.1",
        "https://[::1]/",
        "localhost",
        "se",
        "github.io",
        "not a domain",
        "example.nosuchending",
        "a_b.se",
        "https://",
    ],
)
def test_something_that_is_not_a_domain_is_refused_and_changes_nothing(
    typed: str,
) -> None:
    _, client = business_with_login()
    save(client, "example.se")

    response = save(client, typed)

    assert response.status_code == 200
    assert "not a website domain" in response.content.decode()
    assert saved_domain() == "example.se"


def test_an_empty_value_clears_the_domain() -> None:
    _, client = business_with_login()
    save(client, "example.se")
    save(client, "  ")
    assert saved_domain() == ""


def test_the_settings_page_shows_the_saved_domain() -> None:
    _, client = business_with_login()
    save(client, "https://www.example.se")
    assert 'value="example.se"' in client.get("/settings/").content.decode()


def test_the_dashboard_shows_the_domain_or_that_none_is_set() -> None:
    _, client = business_with_login()
    assert "until you save your website" in client.get("/dashboard/").content.decode()
    save(client, "www.example.se")
    assert (
        ">example.se</strong> and its subdomains"
        in client.get("/dashboard/").content.decode()
    )


def test_the_core_is_not_told_the_domain(settings: Any) -> None:
    business, client = business_with_login()
    save(client, "example.se")

    told = told_to_core(business, settings)

    assert "website_domain" not in told
    assert not schema_errors(told)


@pytest.mark.parametrize(
    "bad",
    [
        "Example.se",  # upper case
        "https://example.se",  # a scheme
        "example.se/shop",  # a path
        "example.se:8443",  # a port
        "example.se ",  # a space
        "example",  # one label
        "-example.se",
        "exa_mple.se",
        "example.se\r\nSet-Cookie: x=1",  # a header line
    ],
)
def test_the_database_refuses_a_stored_domain_that_is_not_clean(bad: str) -> None:
    business, _ = business_with_login()
    # The savepoint keeps the test's own transaction usable after Postgres refuses the write.
    with (
        pytest.raises(
            IntegrityError,
            match="business_website_domain_must_be_empty_or_a_clean_domain",
        ),
        transaction.atomic(),
    ):
        Business.objects.filter(pk=business.pk).update(website_domain=bad)
