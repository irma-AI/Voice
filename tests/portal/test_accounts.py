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
from django.db import IntegrityError, connection, transaction
from django.test import Client

from portal.accounts.invite import invite
from portal.accounts.models import Account, Business

pytestmark = [pytest.mark.db, pytest.mark.django_db]

EMAIL = "user-a@example.com"  # synthetic
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
    invite_as_petter(EMAIL, "Owner A's Salon")
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
    assert "Owner A&#x27;s Salon" in response.content.decode()

    assert client.post("/logout/").status_code == 302
    assert client.get("/dashboard/")["Location"] == "/login/?next=/dashboard/"


def test_the_login_refuses_a_wrong_password_and_the_dashboard_needs_a_login() -> None:
    client = Client()
    invited_with_password(client)
    response = client.post("/login/", {"username": EMAIL, "password": "wrong"})
    assert response.status_code == 200
    assert "That email and password do not match" in response.content.decode()
    assert client.get("/dashboard/").status_code == 302


def test_an_invited_business_that_has_not_set_a_password_cannot_log_in() -> None:
    invite_as_petter(EMAIL, "Owner A's Salon")
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


def test_a_reset_mails_only_the_exact_address_not_a_lookalike() -> None:
    Account.objects.create_user("admin@example.com")
    Account.objects.create_user(
        "adm\u0131n@example.com"
    )  # dotless i: Postgres upper-cases it to I
    Client().post("/password-reset/", {"email": "admin@example.com"})
    assert [m.to for m in mail.outbox] == [["admin@example.com"]]


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
    invite_as_petter(EMAIL, "Owner A's Salon")
    with pytest.raises(CommandError, match="already has an account"):
        invite_as_petter(EMAIL.upper(), "Owner A's Salon")
    assert (len(mail.outbox), Account.objects.count(), Business.objects.count()) == (
        1,
        1,
        1,
    )


def test_an_invitee_whose_link_is_lost_or_expired_asks_for_a_new_one_with_forgot_password() -> (
    None
):
    invite_as_petter(EMAIL, "Owner A's Salon")
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
        "invite_business", EMAIL, "Owner A's Salon", target="local", stdout=StringIO()
    )
    assert (Account.objects.count(), mail.outbox) == (0, [])
    with pytest.raises(CommandError, match="plan changed"):
        call_command(
            "invite_business",
            EMAIL,
            "Owner A's Salon",
            target="local",
            execute=True,
            approved_hash="0" * 64,
        )
    with pytest.raises(CommandError, match="--target production"):
        call_command("invite_business", EMAIL, "Owner A's Salon", target="production")
    assert (Account.objects.count(), mail.outbox) == (0, [])


# What must never break is refused by the database itself, whoever writes.


@contextmanager
def refused(constraint: str) -> Generator[None]:
    # The savepoint keeps the test's own transaction usable after Postgres refuses the write.
    with pytest.raises(IntegrityError, match=constraint), transaction.atomic():
        yield


def test_a_second_business_on_the_same_account_is_refused() -> None:
    account = Account.objects.create_user(EMAIL)
    Business.objects.create(account=account, name="Owner A's Salon")
    with refused("accounts_business_account_id_key"):
        Business.objects.create(account=account, name="Owner A's Other Salon")


def test_a_second_account_for_the_same_email_is_refused_in_any_case() -> None:
    Account.objects.create_user(EMAIL)
    with refused("accounts_account_email_key"):
        Account.objects.create(email=EMAIL)
    with refused("account_email_must_be_clean"):
        Account.objects.create(email=EMAIL.upper())


def test_an_empty_name_is_refused() -> None:
    account = Account.objects.create_user(EMAIL)
    with refused("business_name_must_not_be_blank"):
        Business.objects.create(account=account, name="")
    with refused("business_name_must_not_be_blank"):
        Business.objects.create(account=account, name="  ")


def test_an_email_with_spaces_or_capitals_is_refused_even_by_raw_sql() -> None:
    with connection.cursor() as cur:
        for bad in (" user-a@example.com ", "User-A@example.com"):
            with refused("account_email_must_be_clean"), transaction.atomic():
                cur.execute(
                    "insert into accounts_account (password, email, is_active) values ('', %s, true)",
                    [bad],
                )


def test_an_invite_for_a_bad_address_or_a_blank_name_is_refused_and_leaves_nothing() -> (
    None
):
    for email, name in (
        ("", "Owner A's Salon"),
        ("not an email", "Owner A's Salon"),
        (EMAIL, "  "),
    ):
        with pytest.raises(ValueError):
            invite(name, email)
    assert (Account.objects.count(), Business.objects.count(), mail.outbox) == (
        0,
        0,
        [],
    )


def test_an_invite_that_cannot_be_sent_leaves_no_account_and_does_not_name_the_address(
    settings: Any,
) -> None:
    # A real mail connection to a port nobody listens on.
    settings.MAILERS = {
        "default": {
            "BACKEND": "django.core.mail.backends.smtp.EmailBackend",
            "OPTIONS": {"host": "127.0.0.1", "port": 1},
        }
    }
    with pytest.raises(ValueError) as refused_invite:
        invite("Owner A's Salon", EMAIL)
    assert (
        EMAIL not in str(refused_invite.value)
        and refused_invite.value.__cause__ is None
        and refused_invite.value.__suppress_context__
    )
    assert (Account.objects.count(), Business.objects.count()) == (0, 0)


def test_login_is_refused_after_ten_wrong_passwords_even_with_the_right_one() -> None:
    Account.objects.create_user(EMAIL, PASSWORD)
    client = Client()
    for _ in range(10):
        wrong = client.post("/login/", {"username": EMAIL, "password": "not-it"})
        assert wrong.status_code == 200
    locked = client.post("/login/", {"username": EMAIL, "password": PASSWORD})
    assert locked.status_code == 200 and "Too many failed attempts" in locked.text
    assert "_auth_user_id" not in client.session


def test_a_right_password_resets_the_wrong_ones() -> None:
    Account.objects.create_user(EMAIL, PASSWORD)
    client = Client()
    for _ in range(9):
        client.post("/login/", {"username": EMAIL, "password": "not-it"})
    assert (
        client.post("/login/", {"username": EMAIL, "password": PASSWORD}).status_code
        == 302
    )


def test_a_blank_password_does_not_clear_the_wrong_ones() -> None:
    Account.objects.create_user(EMAIL, PASSWORD)
    client = Client()
    for _ in range(9):
        client.post("/login/", {"username": EMAIL, "password": "not-it"})
    client.post("/login/", {"username": EMAIL, "password": ""})
    client.post("/login/", {"username": EMAIL, "password": "not-it"})
    locked = client.post("/login/", {"username": EMAIL, "password": PASSWORD})
    assert "Too many failed attempts" in locked.text


def test_a_look_alike_spelling_of_the_email_shares_the_count() -> None:
    Account.objects.create_user("a@b.se", PASSWORD)
    client = Client()
    for typed in [
        "a@b.se",
        "ａ@b.se",
    ] * 5:  # the second is a full-width a, which Django treats as the same address
        client.post("/login/", {"username": typed, "password": "not-it"})
    locked = client.post("/login/", {"username": "a@b.se", "password": PASSWORD})
    assert "Too many failed attempts" in locked.text


def test_ten_failures_lock_only_that_address_and_email() -> None:
    Account.objects.create_user(EMAIL, PASSWORD)
    guesser = Client(HTTP_X_FORWARDED_FOR="203.0.113.7")
    for _ in range(10):
        guesser.post("/login/", {"username": EMAIL, "password": "not-it"})
    locked = guesser.post("/login/", {"username": EMAIL, "password": PASSWORD})
    assert "Too many failed attempts" in locked.text
    owner = Client(HTTP_X_FORWARDED_FOR="198.51.100.4")
    assert (
        owner.post("/login/", {"username": EMAIL, "password": PASSWORD}).status_code
        == 302
    )


def test_the_proxy_appended_address_counts_not_the_one_the_client_wrote() -> None:
    Account.objects.create_user(EMAIL, PASSWORD)
    # A new made-up address each try; the proxy appends the real one.
    for n in range(10):
        Client(HTTP_X_FORWARDED_FOR=f"10.0.0.{n}, 203.0.113.7").post(
            "/login/", {"username": EMAIL, "password": "not-it"}
        )
    locked = Client(HTTP_X_FORWARDED_FOR="10.9.9.9, 203.0.113.7").post(
        "/login/", {"username": EMAIL, "password": PASSWORD}
    )
    assert "Too many failed attempts" in locked.text


def test_the_forwarded_header_is_ignored_locally_and_missing_falls_back(
    settings: Any,
) -> None:
    Account.objects.create_user(EMAIL, PASSWORD)
    # A local run: no proxy, so the header is the client's own words.
    settings.DEBUG = True
    for n in range(10):
        Client(HTTP_X_FORWARDED_FOR=f"10.0.0.{n}").post(
            "/login/", {"username": EMAIL, "password": "not-it"}
        )
    assert (
        "Too many failed attempts"
        in Client().post("/login/", {"username": EMAIL, "password": PASSWORD}).text
    )
    settings.DEBUG = False
    # No header behind the proxy: REMOTE_ADDR, the test client's 127.0.0.1.
    for _ in range(10):
        Client().post("/login/", {"username": "b@example.com", "password": "not-it"})
    assert (
        "Too many failed attempts"
        in Client()
        .post("/login/", {"username": "b@example.com", "password": PASSWORD})
        .text
    )


def test_a_sixth_reset_request_in_the_window_sends_nothing_and_looks_the_same() -> None:
    Account.objects.create_user(EMAIL, PASSWORD)
    client = Client(HTTP_X_FORWARDED_FOR="203.0.113.7")
    for _ in range(5):
        client.post("/password-reset/", {"email": EMAIL})
    assert len(mail.outbox) == 5
    sixth = client.post("/password-reset/", {"email": EMAIL})
    assert sixth["Location"] == "/password-reset/sent/"
    assert len(mail.outbox) == 5
