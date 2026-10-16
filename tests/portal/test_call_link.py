# pyright: basic
# (django-stubs types model fields for mypy's plugin; strict pyright cannot read them)
"""A Business's public call link sends anyone to the core with a ticket for that Business only (make test-db).

The ticket is checked by the core's own code (voice/ticket.py), as in tests/portal/test_test_call.py.
"""

import time
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import Client

from portal.accounts.models import Account, Business
from tests.portal.helpers import business_with_login
from voice.ticket import ticket_business

pytestmark = [pytest.mark.db, pytest.mark.django_db]

SECRET = "a-secret-for-tests"


@pytest.fixture(autouse=True)
def core(settings: Any) -> None:
    settings.CORE_SECRET = SECRET
    settings.CORE_URL = "https://voice.example.se/"
    settings.PORTAL_URL = "https://portal.example.se"


def test_the_link_sends_anyone_to_the_core_with_a_ticket_for_that_business() -> None:
    anna, _ = business_with_login("anna.testsson@example.com", "Anna's Salon")
    bo, _ = business_with_login("bo.testsson@example.com", "Bo's Bikes")

    response = Client().get(f"/call/{anna.call_slug}/")  # no login

    assert response.status_code == 302
    parts = urlsplit(response["Location"])
    assert (parts.scheme, parts.netloc, parts.path) == (
        "https",
        "voice.example.se",
        "/",
    )
    ticket = parse_qs(parts.query)["ticket"][0]
    assert ticket_business(ticket, SECRET) == anna.pk != bo.pk
    assert ticket_business(ticket, SECRET, time.time() + 3600) is None


def test_the_link_cannot_be_guessed_and_only_reads() -> None:
    anna, _ = business_with_login("anna.testsson@example.com", "Anna's Salon")
    assert Client().get("/call/not-a-link/").status_code == 404
    assert (
        Client().get(f"/call/{anna.pk}/").status_code == 404
    )  # the number is not the link
    assert Client().post(f"/call/{anna.call_slug}/").status_code == 405


def test_a_portal_with_no_secret_sends_nobody_to_the_core(settings: Any) -> None:
    anna, _ = business_with_login("anna.testsson@example.com", "Anna's Salon")
    settings.CORE_SECRET = ""
    response = Client().get(f"/call/{anna.call_slug}/")
    assert response.status_code == 503 and "Location" not in response


def test_every_business_has_its_own_link_and_the_database_refuses_a_shared_one() -> (
    None
):
    anna, _ = business_with_login("anna.testsson@example.com", "Anna's Salon")
    bo, _ = business_with_login("bo.testsson@example.com", "Bo's Bikes")
    assert anna.call_slug != bo.call_slug and len(anna.call_slug) >= 20
    with pytest.raises(IntegrityError), transaction.atomic():
        Business.objects.filter(pk=bo.pk).update(call_slug=anna.call_slug)


def test_the_dashboard_shows_a_business_its_own_link() -> None:
    anna, client = business_with_login("anna.testsson@example.com", "Anna's Salon")
    bo, _ = business_with_login("bo.testsson@example.com", "Bo's Bikes")
    page = client.get("/dashboard/").content.decode()
    assert f"https://portal.example.se/call/{anna.call_slug}/" in page
    assert bo.call_slug not in page


def test_a_business_cannot_set_its_own_link_from_the_settings_page() -> None:
    anna, client = business_with_login("anna.testsson@example.com", "Anna's Salon")
    client.post(
        "/settings/",
        {"name": "Anna's Salon", "facts": "", "languages": ["sv"], "call_slug": "mine"},
    )
    anna.refresh_from_db()
    assert anna.call_slug != "mine"


@pytest.mark.django_db(transaction=True)
def test_businesses_that_exist_before_the_link_each_get_their_own() -> None:
    executor = MigrationExecutor(connection)
    before = [("accounts", "0004_module_limit")]
    executor.migrate(before)
    old = executor.loader.project_state(before).apps
    for n in range(3):
        account = old.get_model("accounts", "Account").objects.create(
            email=f"old{n}@example.com"
        )
        old.get_model("accounts", "Business").objects.create(
            account=account, name=f"Old {n}"
        )

    executor = MigrationExecutor(connection)
    executor.migrate(executor.loader.graph.leaf_nodes())

    slugs = list(Business.objects.values_list("call_slug", flat=True))
    assert len(slugs) == 3 and len(set(slugs)) == 3 and all(slugs)
    assert Account.objects.count() == 3
