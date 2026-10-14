"""The Portal through its web pages and its database (make test-db). No mocks of our own code."""

import re
from collections.abc import Generator
from contextlib import contextmanager
from io import StringIO
from typing import Any
from urllib.parse import urlsplit

import pytest
from django.core import mail
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, transaction
from django.test import Client

from portal.accounts.models import Account, Business

pytestmark = [pytest.mark.db, pytest.mark.django_db]

EMAIL = "anna.testsson@example.com"  # synthetic
PASSWORD = "a-long-passphrase-for-tests"


def link_in(message: Any) -> str:
    match = re.search(r"https?://\S+", message.body)
    assert match, message.body
    link = urlsplit(match.group(0))
    assert (link.scheme, link.netloc) == (
        "http",
        "localhost:8000",
    )  # PORTAL_URL, never the request's Host
    return link.path


def set_password(client: Client, link: str, password: str) -> None:
    # Django swaps the token in the link for a session-bound address on the first visit.
    set_url = client.get(link, follow=False)["Location"]
    response = client.post(
        set_url, {"new_password1": password, "new_password2": password}
    )
    assert response.status_code == 302, response.content.decode()
    assert response["Location"] == "/password-reset/done/"


def invite_as_petter(email: str, name: str) -> None:
    """The reviewed way: a dry run prints the plan and its hash, and only that hash lets --execute run."""
    dry = StringIO()
    call_command("invite_business", email, name, target="local", stdout=dry)
    digest = re.search(r"plan sha256: (\w+)", dry.getvalue())
    assert digest
    call_command(
        "invite_business",
        email,
        name,
        target="local",
        execute=True,
        approved_hash=digest.group(1),
        stdout=StringIO(),
    )


def invited_with_password(client: Client) -> None:
    invite_as_petter(EMAIL, "Anna's Salon")
    set_password(client, link_in(mail.outbox[-1]), PASSWORD)


def test_an_invited_business_sets_a_password_logs_in_sees_its_dashboard_and_logs_out() -> (
    None
):
    client = Client()
    invited_with_password(client)
    assert mail.outbox[0].to == [EMAIL]

    # The login accepts the email in any case, and an empty dashboard greets the Business by name.
    response = client.post(
        "/login/", {"username": EMAIL.upper(), "password": PASSWORD}, follow=True
    )
    assert response.redirect_chain == [("/dashboard/", 302)]
    assert "Anna&#x27;s Salon" in response.content.decode()

    assert client.post("/logout/").status_code == 302
    assert client.get("/dashboard/")["Location"] == "/login/?next=/dashboard/"


def test_the_login_refuses_a_wrong_password_and_the_dashboard_needs_a_login() -> None:
    client = Client()
    invited_with_password(client)
    response = client.post("/login/", {"username": EMAIL, "password": "wrong"})
    assert response.status_code == 200
    assert "Please enter a correct" in response.content.decode()
    assert client.get("/dashboard/").status_code == 302


def test_an_invited_business_that_has_not_set_a_password_cannot_log_in() -> None:
    invite_as_petter(EMAIL, "Anna's Salon")
    assert (
        Client().post("/login/", {"username": EMAIL, "password": ""}).status_code == 200
    )
    assert not Client().login(email=EMAIL, password="")


def test_a_forgotten_password_is_reset_by_email() -> None:
    client = Client()
    invited_with_password(client)
    mail.outbox.clear()

    assert client.post("/password-reset/", {"email": EMAIL}).status_code == 302
    set_password(client, link_in(mail.outbox[0]), "another-long-passphrase")

    assert (
        Client().post("/login/", {"username": EMAIL, "password": PASSWORD}).status_code
        == 200
    )  # the old one is refused
    assert (
        Client()
        .post("/login/", {"username": EMAIL, "password": "another-long-passphrase"})
        .status_code
        == 302
    )


def test_a_reset_for_an_unknown_email_looks_the_same_and_sends_nothing() -> None:
    response = Client().post("/password-reset/", {"email": "nobody@example.com"})
    assert response["Location"] == "/password-reset/sent/"
    assert mail.outbox == []


def test_a_used_reset_link_no_longer_works() -> None:
    client = Client()
    invited_with_password(client)
    used = link_in(mail.outbox[0])
    assert "no longer works" in Client().get(used, follow=True).content.decode()


def test_an_email_that_already_has_an_account_is_not_invited_again() -> None:
    invite_as_petter(EMAIL, "Anna's Salon")
    with pytest.raises(CommandError, match="already has an account"):
        invite_as_petter(EMAIL.upper(), "Anna's Salon")
    assert (len(mail.outbox), Account.objects.count(), Business.objects.count()) == (
        1,
        1,
        1,
    )


def test_an_invitee_whose_link_is_lost_or_expired_asks_for_a_new_one_with_forgot_password() -> (
    None
):
    invite_as_petter(EMAIL, "Anna's Salon")
    mail.outbox.clear()
    Client().post("/password-reset/", {"email": EMAIL})
    set_password(Client(), link_in(mail.outbox[0]), PASSWORD)
    assert (
        Client().post("/login/", {"username": EMAIL, "password": PASSWORD}).status_code
        == 302
    )


def test_the_invite_command_changes_nothing_without_the_reviewed_hash_or_for_the_wrong_target() -> (
    None
):
    call_command(
        "invite_business", EMAIL, "Anna's Salon", target="local", stdout=StringIO()
    )
    assert (Account.objects.count(), mail.outbox) == (0, [])
    with pytest.raises(CommandError, match="plan changed"):
        call_command(
            "invite_business",
            EMAIL,
            "Anna's Salon",
            target="local",
            execute=True,
            approved_hash="0" * 64,
        )
    with pytest.raises(CommandError, match="--target production"):
        call_command("invite_business", EMAIL, "Anna's Salon", target="production")
    assert (Account.objects.count(), mail.outbox) == (0, [])


def test_the_public_page_links_to_the_login() -> None:
    assert 'href="/login/"' in Client().get("/").content.decode()


# What must never break is refused by the database itself, whoever writes.


@contextmanager
def refused(constraint: str) -> Generator[None]:
    # The savepoint keeps the test's own transaction usable after Postgres refuses the write.
    with pytest.raises(IntegrityError, match=constraint), transaction.atomic():
        yield


def test_a_second_business_on_the_same_account_is_refused() -> None:
    account = Account.objects.create_user(EMAIL)
    Business.objects.create(account=account, name="Anna's Salon")
    with refused("accounts_business_account_id_key"):
        Business.objects.create(account=account, name="Anna's Other Salon")


def test_a_second_account_for_the_same_email_is_refused_in_any_case() -> None:
    Account.objects.create_user(EMAIL)
    with refused("accounts_account_email_key"):
        Account.objects.create(email=EMAIL)
    with refused("account_email_must_be_lowercase"):
        Account.objects.create(email=EMAIL.upper())


def test_a_negative_limit_or_an_empty_name_is_refused() -> None:
    account = Account.objects.create_user(EMAIL)
    with refused("business_calls_per_day_must_not_be_negative"):
        Business.objects.create(account=account, name="A", max_calls_per_day=-1)
    with refused("business_minutes_per_day_must_not_be_negative"):
        Business.objects.create(account=account, name="A", max_minutes_per_day=-1)
    with refused("business_name_must_not_be_blank"):
        Business.objects.create(account=account, name="")
    with refused("business_name_must_not_be_blank"):
        Business.objects.create(account=account, name="  ")
