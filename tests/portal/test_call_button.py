# pyright: basic
# (django-stubs types model fields for mypy's plugin; strict pyright cannot read them)
"""The call button on a Business's website starts a call only from the websites the Business listed (make test-db).

The ticket is checked by the core's own code (voice/ticket.py), as in tests/portal/test_call_link.py.
"""

from html import unescape
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from django.db import IntegrityError, connection, transaction
from django.test import Client
from django.urls import reverse

from portal.accounts.models import Business
from portal.accounts.website import ADDRESSES_MAX, ORIGIN_PATTERN, parse_addresses
from tests.portal.helpers import business_with_login
from voice.ticket import ticket_business

pytestmark = [pytest.mark.db, pytest.mark.django_db]

SECRET = "a-secret-for-tests"
SITE = "https://www.annas-salon.example"


@pytest.fixture(autouse=True)
def core(settings: Any) -> None:
    settings.CORE_SECRET = SECRET
    settings.CORE_URL = "https://voice.example.se/"
    settings.PORTAL_URL = "https://portal.example.se"


def press_button(business: Business, origin: str | None) -> Any:
    """What a browser sends when the button on a page at `origin` asks for a ticket."""
    headers = {} if origin is None else {"Origin": origin}
    return Client().get(f"/call/{business.call_slug}/button/", headers=headers)


def listing(business: Business, *sites: str) -> Business:
    business.website_addresses = list(sites)
    business.save()
    return business


def test_a_listed_website_gets_a_ticket_for_that_business_only() -> None:
    anna, _ = business_with_login("anna.testsson@example.com", "Anna's Salon")
    bo, _ = business_with_login("bo.testsson@example.com", "Bo's Bikes")
    listing(anna, SITE)

    response = press_button(anna, SITE)

    assert response.status_code == 200
    assert (
        response["Access-Control-Allow-Origin"] == SITE
    )  # the browser then lets the page read it
    assert "Origin" in response["Vary"]
    parts = urlsplit(response.json()["url"])
    assert (parts.scheme, parts.netloc, parts.path) == (
        "https",
        "voice.example.se",
        "/",
    )
    ticket = parse_qs(parts.query)["ticket"][0]
    assert ticket_business(ticket, SECRET) == anna.pk != bo.pk


def test_any_other_page_gets_no_ticket_and_no_permission_to_read_the_answer() -> None:
    anna, _ = business_with_login("anna.testsson@example.com", "Anna's Salon")
    bo, _ = business_with_login("bo.testsson@example.com", "Bo's Bikes")
    listing(anna, SITE)
    listing(bo, "https://bos-bikes.example")

    others = [
        None,  # no Origin at all (not a page in a browser)
        "",
        "null",  # a sandboxed page
        "https://evil.example",
        "https://bos-bikes.example",  # listed, but by another Business
        SITE + ".evil.example",  # starts with a listed address
        "https://evil.example/" + SITE,
        "http://www.annas-salon.example",  # same host, other scheme
        SITE + ":8443",  # same host, other port
        SITE.upper(),
        SITE + "/",
    ]
    for origin in others:
        response = press_button(anna, origin)
        assert response.status_code == 403, origin
        assert "Access-Control-Allow-Origin" not in response, origin
        assert "ticket" not in response.content.decode(), origin


def test_a_business_that_lists_nothing_is_open_to_no_website() -> None:
    anna, _ = business_with_login("anna.testsson@example.com", "Anna's Salon")
    assert anna.website_addresses == []
    assert press_button(anna, SITE).status_code == 403
    assert press_button(anna, None).status_code == 403


def test_only_the_businesss_own_link_works_and_only_to_read(settings: Any) -> None:
    anna, _ = business_with_login("anna.testsson@example.com", "Anna's Salon")
    listing(anna, SITE)
    assert (
        Client().get("/call/not-a-link/button/", headers={"Origin": SITE}).status_code
        == 404
    )
    assert (
        Client()
        .post(f"/call/{anna.call_slug}/button/", headers={"Origin": SITE})
        .status_code
        == 405
    )
    settings.CORE_SECRET = ""
    response = press_button(anna, SITE)
    assert response.status_code == 503 and "url" not in response.json()


def test_the_script_asks_the_address_the_portal_serves() -> None:
    # The path lives in call-button.js and in portal/urls.py: the test names the side to edit.
    script = (
        Path(__file__).parents[2] / "portal/static/portal/call-button.js"
    ).read_text("utf-8")
    before, after = reverse("call_from_site", args=["SLUG"]).split("SLUG")
    assert f'"{before}"' in script and f'"{after}"' in script, (
        "portal/static/portal/call-button.js and portal/urls.py disagree on the button's address: edit the one that changed"
    )


def test_the_database_rule_and_the_form_rule_for_a_website_are_the_same() -> None:
    # The pattern and the limit live in portal/accounts/website.py and, frozen, in migration 0006: the test names the side to edit.
    migration = (
        Path(__file__).parents[2]
        / "portal/accounts/migrations/0006_business_website_addresses.py"
    ).read_text("utf-8")
    assert ORIGIN_PATTERN in migration, (
        "website.py ORIGIN_PATTERN changed: a shipped migration does not change, so add a migration that replaces the check in 0006"
    )
    limit = f"business_must_list_at_most_{ADDRESSES_MAX}_websites"
    assert limit in {c.name for c in Business._meta.constraints}, (
        "website.py ADDRESSES_MAX changed: add a migration that replaces the limit's constraint, and rename it in models.py"
    )


def test_a_business_lists_its_websites_and_the_page_shows_its_own_snippet() -> None:
    anna, client = business_with_login("anna.testsson@example.com", "Anna's Salon")
    bo, _ = business_with_login("bo.testsson@example.com", "Bo's Bikes")

    response = client.post(
        "/website-button/",
        {
            "addresses": f"{SITE}/\nHTTPS://Annas-Salon.example:443\n\nhttps://shop.annas-salon.example:8443\n{SITE}"
        },
    )

    assert response["Location"] == "/website-button/?saved=1"
    anna.refresh_from_db()
    assert anna.website_addresses == [
        SITE,
        "https://annas-salon.example",
        "https://shop.annas-salon.example:8443",
    ]  # the spelling a browser sends, repeats dropped
    page = unescape(client.get(response["Location"]).content.decode())
    assert "Saved." in page
    assert f'data-call="{anna.call_slug}"' in page and bo.call_slug not in page
    assert 'src="https://portal.example.se/static/portal/call-button.js"' in page


def test_a_swedish_letter_in_the_address_is_written_the_way_the_browser_sends_it() -> (
    None
):
    assert parse_addresses("https://räksmörgås.se") == ["https://xn--rksmrgs-5wao1o.se"]


def test_a_bad_list_is_refused_and_changes_nothing() -> None:
    anna, client = business_with_login("anna.testsson@example.com", "Anna's Salon")
    listing(anna, SITE)
    bad = [
        "http://annas-salon.example",  # not https
        "https://annas-salon.example/boka",  # a page, not a website
        "https://*.annas-salon.example",
        "https://annas-salon.example?x=1",
        "https://user:pw@annas-salon.example",
        "annas-salon.example",
        "https://",
        "https://annas-salon.example:99999",
        "\n".join(f"https://site{n}.example" for n in range(ADDRESSES_MAX + 1)),
    ]
    for text in bad:
        response = client.post("/website-button/", {"addresses": text})
        assert (
            response.status_code == 200 and "errorlist" in response.content.decode()
        ), text
        anna.refresh_from_db()
        assert anna.website_addresses == [SITE], text


def test_a_business_can_clear_its_list_and_cannot_edit_another_businesss() -> None:
    anna, client = business_with_login("anna.testsson@example.com", "Anna's Salon")
    bo, _ = business_with_login("bo.testsson@example.com", "Bo's Bikes")
    listing(anna, SITE)
    listing(bo, "https://bos-bikes.example")

    client.post(
        "/website-button/", {"addresses": "", "business": bo.pk, "business_id": bo.pk}
    )

    anna.refresh_from_db()
    bo.refresh_from_db()
    assert anna.website_addresses == []
    assert bo.website_addresses == ["https://bos-bikes.example"]


def test_the_database_refuses_a_website_that_is_not_a_plain_https_origin() -> None:
    anna, _ = business_with_login("anna.testsson@example.com", "Anna's Salon")
    for bad in [
        "http://annas-salon.example",
        "https://*.annas-salon.example",
        "https://annas-salon.example/boka",
        "https://Annas-Salon.example",
        "https://annas-salon.example ",
        "https://a.example https://b.example",
        "https://.example",
        "*",
        "",
    ]:
        with (
            pytest.raises(
                IntegrityError, match="business_websites_must_be_plain_https_origins"
            ),
            transaction.atomic(),
        ):
            Business.objects.filter(pk=anna.pk).update(website_addresses=[SITE, bad])


def test_the_database_refuses_a_sixth_website() -> None:
    anna, _ = business_with_login("anna.testsson@example.com", "Anna's Salon")
    Business.objects.filter(pk=anna.pk).update(
        website_addresses=[f"https://site{n}.example" for n in range(ADDRESSES_MAX)]
    )
    with (
        pytest.raises(IntegrityError, match="business_must_list_at_most_5_websites"),
        transaction.atomic(),
    ):
        Business.objects.filter(pk=anna.pk).update(
            website_addresses=[
                f"https://site{n}.example" for n in range(ADDRESSES_MAX + 1)
            ]
        )


def test_the_database_refuses_an_empty_slot_in_the_list() -> None:
    anna, _ = business_with_login("anna.testsson@example.com", "Anna's Salon")
    with (
        pytest.raises(
            IntegrityError, match="business_websites_must_be_plain_https_origins"
        ),
        transaction.atomic(),
        connection.cursor() as cursor,
    ):
        cursor.execute(
            "UPDATE accounts_business SET website_addresses = ARRAY[NULL]::varchar[] WHERE id = %s",
            [anna.pk],
        )
