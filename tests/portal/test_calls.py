# pyright: basic
# (django-stubs types model fields for mypy's plugin; strict pyright cannot read them)
"""A call may start only when the Business is on and under its limits; the Portal counts, the core obeys (make test-db).

The rules are the Portal's (`Business.start_call`), the address the core asks is `/api/businesses/<id>/calls/`, and the core's own
code (voice/calls.py) talks to the real Portal here, so a drift between the two names the side to edit. No mocks of our own code.
"""

import json
import re
import time
from datetime import timedelta
from io import StringIO
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import Client
from django.utils import timezone

from portal.accounts.models import (
    LIMIT,
    LONGEST_CALL_SECONDS,
    OFF,
    Account,
    Business,
    Call,
)
from tests.portal.helpers import business_with_login
from voice.calls import REFUSED, NotLetStart, finish, start
from voice.serve import MAX_CALL_SECS
from voice.settings import SettingsRefused, load_settings
from voice.ticket import ticket_business

pytestmark = [pytest.mark.db, pytest.mark.django_db]

SECRET = "a-secret-for-tests"
ANNA = "anna.testsson@example.com"


@pytest.fixture(autouse=True)
def core(settings: Any) -> None:
    settings.CORE_SECRET = SECRET
    settings.CORE_URL = "https://voice.example.se/"
    settings.PORTAL_URL = "https://portal.example.se"


def anna(**fields: Any) -> Business:
    business, _ = business_with_login(ANNA, "Anna's Salon")
    Business.objects.filter(pk=business.pk).update(**fields)
    business.refresh_from_db()
    return business


def ask(path: str, body: object = None, secret: str | None = SECRET) -> Any:
    headers = {} if secret is None else {"Authorization": f"Bearer {secret}"}
    return Client().post(
        path,
        json.dumps(body if body is not None else {}),
        content_type="application/json",
        headers=headers,
    )


def midnight() -> Any:
    return timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)


# The rules.


def test_a_call_is_let_start_and_recorded_until_the_calls_per_day_run_out() -> None:
    business = anna(max_calls_per_day=2)
    assert isinstance(business.start_call(), Call)
    assert isinstance(business.start_call(), Call)
    assert business.start_call() == LIMIT
    assert (
        Call.objects.filter(business=business).count() == 2
    )  # the refused call left no trace


@pytest.mark.parametrize("field", ["max_calls_per_day", "max_minutes_per_day"])
def test_a_zero_limit_lets_no_call_start(field: str) -> None:
    assert anna(**{field: 0}).start_call() == LIMIT


def test_minutes_run_out_by_the_length_the_core_reported() -> None:
    business = anna(max_minutes_per_day=30)
    Call.objects.create(business=business, seconds=29 * 60)
    assert isinstance(business.start_call(), Call)  # a minute left: one more may begin
    Call.objects.all().delete()
    Call.objects.create(business=business, seconds=30 * 60)
    assert business.start_call() == LIMIT


def test_a_call_whose_end_was_never_reported_counts_as_the_longest_a_call_can_be() -> (
    None
):
    business = anna(max_minutes_per_day=LONGEST_CALL_SECONDS // 60)
    assert isinstance(business.start_call(), Call)
    assert business.used_today() == (1, LONGEST_CALL_SECONDS)
    assert business.start_call() == LIMIT


def test_a_switched_off_business_is_refused_whatever_it_has_left() -> None:
    business = anna(enabled=False)
    assert business.start_call() == OFF
    assert Call.objects.filter(business=business).count() == 0
    Business.objects.filter(pk=business.pk).update(enabled=True)
    assert isinstance(Business.objects.get().start_call(), Call)


def test_yesterdays_calls_do_not_count_and_another_businesss_calls_do_not_either() -> (
    None
):
    business = anna(max_calls_per_day=1)
    Call.objects.create(
        business=business,
        started_at=midnight() - timedelta(seconds=1),
        seconds=LONGEST_CALL_SECONDS,
    )
    other, _ = business_with_login("bo.testsson@example.com", "Bo's Bikes")
    Call.objects.create(business=other, seconds=5)
    assert business.used_today() == (0, 0)
    assert isinstance(business.start_call(), Call)


# The address the core asks.


def test_the_core_is_told_yes_with_the_calls_number_or_no_with_the_reason() -> None:
    business = anna(max_calls_per_day=1)
    path = f"/api/businesses/{business.pk}/calls/"

    yes = ask(path)
    assert (yes.status_code, yes.json()) == (201, {"call": Call.objects.get().pk})

    no = ask(path)
    assert (no.status_code, no.json()) == (403, {"refused": LIMIT})

    Business.objects.filter(pk=business.pk).update(enabled=False)
    assert ask(path).json() == {"refused": OFF}
    assert Call.objects.count() == 1


def test_the_start_address_refuses_a_missing_or_wrong_secret_before_it_looks_anything_up() -> (
    None
):
    business = anna()
    for secret in (None, "", "wrong", SECRET + "x"):
        assert (
            ask(f"/api/businesses/{business.pk}/calls/", secret=secret).status_code
            == 401
        )
        assert ask("/api/businesses/999999/calls/", secret=secret).status_code == 401
    assert ask("/api/businesses/999999/calls/").status_code == 404
    assert Call.objects.count() == 0


def test_the_start_address_refuses_everyone_when_no_secret_is_set(
    settings: Any,
) -> None:
    settings.CORE_SECRET = ""
    business = anna()
    assert ask(f"/api/businesses/{business.pk}/calls/", secret="").status_code == 401


def test_the_start_address_needs_no_csrf_token_but_only_takes_a_post() -> None:
    business = anna()
    path = f"/api/businesses/{business.pk}/calls/"
    strict = Client(enforce_csrf_checks=True)
    assert (
        strict.post(
            path,
            "{}",
            content_type="application/json",
            headers={"Authorization": f"Bearer {SECRET}"},
        ).status_code
        == 201
    )  # the core has no browser session to carry a token
    assert (
        Client().get(path, headers={"Authorization": f"Bearer {SECRET}"}).status_code
        == 405
    )


def test_the_end_of_a_call_is_stored_once_and_never_longer_than_a_call_can_run() -> (
    None
):
    call = anna().start_call()
    assert isinstance(call, Call)
    path = f"/api/calls/{call.pk}/end/"

    assert ask(path, {"seconds": 95}).status_code == 200
    assert Call.objects.get().seconds == 95
    assert (
        ask(path, {"seconds": 5}).status_code == 200
    )  # a second report changes nothing
    assert Call.objects.get().seconds == 95

    other = Call.objects.create(business=call.business)
    ask(f"/api/calls/{other.pk}/end/", {"seconds": 10**12})
    assert Call.objects.get(pk=other.pk).seconds == LONGEST_CALL_SECONDS


@pytest.mark.parametrize(
    "body", [{}, {"seconds": "soon"}, {"seconds": -1}, {"seconds": None}, [1]]
)
def test_a_report_that_is_not_a_whole_number_of_seconds_is_refused(body: Any) -> None:
    call = anna().start_call()
    assert isinstance(call, Call)
    assert ask(f"/api/calls/{call.pk}/end/", body).status_code == 400
    assert Call.objects.get().seconds is None


def test_the_end_address_wants_the_secret_and_a_call_that_exists() -> None:
    call = anna().start_call()
    assert isinstance(call, Call)
    for secret in (None, "wrong"):
        assert (
            ask(f"/api/calls/{call.pk}/end/", {"seconds": 1}, secret).status_code == 401
        )
    assert ask("/api/calls/999999/end/", {"seconds": 1}).status_code == 404
    assert Call.objects.get().seconds is None


def test_the_core_s_own_code_is_let_start_and_refused_by_the_real_portal(
    live_server: Any,
) -> None:
    business = anna(max_calls_per_day=1)
    env = {"SETTINGS_URL": live_server.url, "CORE_SECRET": SECRET}
    settings = load_settings({**env, "BUSINESS_ID": str(business.pk)})
    drift = "voice/calls.py and portal/accounts/views.py disagree: edit the one that changed"

    call = start(settings, env)
    assert call is not None and Call.objects.get().pk == call.id, drift
    finish(call, env)
    assert Call.objects.get().seconds is not None, drift

    with pytest.raises(NotLetStart) as no:
        start(settings, env)
    assert no.value.text == REFUSED[LIMIT], drift
    Business.objects.filter(pk=business.pk).update(enabled=False)
    with pytest.raises(NotLetStart) as off:
        start(settings, env)
    assert off.value.text == REFUSED[OFF], drift

    with pytest.raises(SettingsRefused):  # a Portal that does not know the secret
        start(settings, {**env, "CORE_SECRET": "wrong"})


def test_the_two_services_agree_on_the_reasons_and_the_longest_call() -> None:
    assert set(REFUSED) == {OFF, LIMIT}, (
        "portal/accounts/models.py OFF and LIMIT and voice/calls.py REFUSED disagree: edit the one that changed"
    )
    assert LONGEST_CALL_SECONDS == MAX_CALL_SECS, (
        "portal/accounts/models.py LONGEST_CALL_SECONDS and voice/serve.py MAX_CALL_SECS disagree: edit the one that changed"
    )


# The public call link.


def test_the_call_link_sends_anyone_to_the_core_with_a_ticket_for_that_business() -> (
    None
):
    business = anna()
    other, _ = business_with_login("bo.testsson@example.com", "Bo's Bikes")

    response = Client().get(f"/call/{business.call_slug}/")  # no login

    assert response.status_code == 302
    parts = urlsplit(response["Location"])
    assert (parts.scheme, parts.netloc, parts.path) == (
        "https",
        "voice.example.se",
        "/",
    )
    ticket = parse_qs(parts.query)["ticket"][0]
    assert ticket_business(ticket, SECRET) == business.pk != other.pk
    assert ticket_business(ticket, SECRET, time.time() + 3600) is None


def test_the_call_link_does_not_guess_does_not_start_a_call_and_only_reads() -> None:
    business = anna()
    assert Client().get("/call/not-a-link/").status_code == 404
    assert (
        Client().get(f"/call/{business.pk}/").status_code == 404
    )  # the number is not the link
    assert Client().post(f"/call/{business.call_slug}/").status_code == 405
    assert (
        Call.objects.count() == 0
    )  # opening the link spends nothing: the core counts a call when it starts


def test_a_switched_off_business_still_has_a_link_and_the_core_is_what_refuses() -> (
    None
):
    business = anna(enabled=False)
    assert Client().get(f"/call/{business.call_slug}/").status_code == 302


def test_a_portal_with_no_secret_sends_nobody_to_the_core(settings: Any) -> None:
    business = anna()
    settings.CORE_SECRET = ""
    response = Client().get(f"/call/{business.call_slug}/")
    assert response.status_code == 503 and "Location" not in response


def test_every_business_has_its_own_link_and_the_database_refuses_a_shared_one() -> (
    None
):
    first = anna()
    second, _ = business_with_login("bo.testsson@example.com", "Bo's Bikes")
    assert first.call_slug != second.call_slug and len(first.call_slug) >= 20
    with pytest.raises(IntegrityError), transaction.atomic():
        Business.objects.filter(pk=second.pk).update(call_slug=first.call_slug)


def test_the_database_refuses_a_negative_length_for_a_call() -> None:
    business = anna()
    with (
        pytest.raises(IntegrityError, match="call_seconds_must_not_be_negative"),
        transaction.atomic(),
    ):
        Call.objects.create(business=business, seconds=-1)


# What the Business sees.


def test_the_dashboard_shows_the_state_the_usage_and_the_link() -> None:
    business, client = business_with_login(ANNA, "Anna's Salon")
    Call.objects.create(business=business, seconds=125)
    page = client.get("/dashboard/").content.decode()
    assert "Your agent takes calls." in page
    assert "1 of 10 calls, 3 of 30 minutes" in page
    assert f"https://portal.example.se/call/{business.call_slug}/" in page

    Business.objects.filter(pk=business.pk).update(enabled=False)
    assert "switched off" in client.get("/dashboard/").content.decode()


def test_a_business_cannot_change_its_own_limits_or_switch_from_its_settings_page() -> (
    None
):
    business, client = business_with_login(ANNA, "Anna's Salon")
    client.post(
        "/settings/",
        {
            "name": "Anna's Salon",
            "facts": "",
            "languages": ["sv"],
            "max_calls_per_day": 100000,
            "max_minutes_per_day": 100000,
            "enabled": "",
            "call_slug": "mine",
        },
    )
    business.refresh_from_db()
    assert (business.max_calls_per_day, business.max_minutes_per_day) == (10, 30)
    assert business.enabled and business.call_slug != "mine"


# Petter's command: the one way the switch and the limits change.


def configure(*args: str, **options: Any) -> str:
    out = StringIO()
    call_command(
        "configure_business", ANNA, *args, target="local", stdout=out, **options
    )
    return out.getvalue()


def reviewed(*args: str) -> None:
    digest = re.search(r"plan sha256: (\w+)", configure(*args))
    assert digest
    configure(*args, execute=True, approved_hash=digest.group(1))


def test_the_command_changes_nothing_without_the_reviewed_hash_or_for_the_wrong_target() -> (
    None
):
    anna()
    assert "dry run" in configure("--enabled", "off", "--max-calls-per-day", "3")
    assert (
        Business.objects.get().enabled
        and Business.objects.get().max_calls_per_day == 10
    )
    with pytest.raises(CommandError, match="plan changed"):
        configure("--enabled", "off", execute=True, approved_hash="0" * 64)
    with pytest.raises(CommandError, match="--target production"):
        call_command(
            "configure_business", ANNA, "--enabled", "off", target="production"
        )
    assert Business.objects.get().enabled


def test_the_command_switches_a_business_off_and_sets_its_limits_after_review() -> None:
    anna()
    reviewed(
        "--enabled", "off", "--max-calls-per-day", "3", "--max-minutes-per-day", "9"
    )
    business = Business.objects.get()
    assert (
        business.enabled,
        business.max_calls_per_day,
        business.max_minutes_per_day,
    ) == (
        False,
        3,
        9,
    )
    reviewed("--enabled", "on")
    assert Business.objects.get().enabled


def test_the_command_refuses_a_negative_limit_an_unknown_business_and_an_empty_plan() -> (
    None
):
    anna()
    with pytest.raises(CommandError, match="must not be negative"):
        configure("--max-calls-per-day", "-1")
    with pytest.raises(CommandError, match="nothing to change"):
        configure()
    with pytest.raises(CommandError, match="no Business has that email"):
        call_command(
            "configure_business",
            "nobody@example.com",
            "--enabled",
            "off",
            target="local",
        )


# Migrating a Portal that already has Businesses.


@pytest.mark.django_db(transaction=True)
def test_businesses_that_exist_before_the_call_link_each_get_their_own() -> None:
    executor = MigrationExecutor(connection)
    before = [("accounts", "0002_business_facts_business_languages_and_more")]
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
