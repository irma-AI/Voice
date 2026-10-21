"""`make seed`: fills the local Portal with the same synthetic data on every run (VOI-259). Local only, never a copy of production."""

# pyright: basic
# (django-stubs types model fields for mypy's plugin; strict pyright cannot read them)

import os
from datetime import timedelta
from decimal import Decimal

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "portal.settings")
django.setup()  # before the imports below: the models need the app registry

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from portal import synthetic
from portal.accounts import changes
from portal.accounts.models import (
    CALL_KINDS,
    AccessToken,
    Account,
    Business,
    CallLog,
    CallRecord,
    Module,
)

PASSWORD = (
    "seeded-local-only"  # not a secret: the seed runs only against a local database
)
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
# Voice's own Postgres: compose.yml (make portal-up) and compose.test.yml (make test-db); tests/portal/test_seed.py reads both.
# A port check too, so a tunnel on this machine to a shared database is refused.
LOCAL_PORTS = {"55431", "55432"}


class Refused(Exception):
    pass


def check_local(environment: str, host: str, port: str) -> None:
    """Fails closed: the seed writes only to a local database in a local environment, so the invite stays the one way in elsewhere (VOI-32)."""
    if environment != "local":
        raise Refused(f"ENVIRONMENT is {environment!r}, not local")
    if host not in LOCAL_HOSTS:
        raise Refused(f"the database host is {host!r}, not this machine")
    if port not in LOCAL_PORTS:
        raise Refused(f"the database port is {port!r}, not Voice's own local Postgres")


def a_business(nth: int, email: str) -> Business:
    fake = synthetic.fake
    account = Account.objects.create_user(email, PASSWORD)
    name = synthetic.business_name()
    business = Business.objects.create(
        account=account,
        name=name,
        instructions=f"Du svarar i telefon för {name}. Vi har öppet vardagar 9–17 och nås på {synthetic.phone_number()}. "
        "Hänvisa bokningar till hemsidan.",
        accent=fake.hex_color(),
        website_domain="example.com",  # reserved, so no real company's logo is fetched
    )
    Module.objects.create(
        business=business,
        name="hours",
        command="python",
        args=["-m", "modules.example"],
    )
    now = timezone.now()
    for _ in range(12 + nth * 6):
        CallRecord.objects.create(
            call_id=fake.hexify("^^^^^^-^^^^^^^^^^"),
            business=business,
            kind=fake.random_element(list(CALL_KINDS)),
            started_at=now - timedelta(minutes=fake.random_int(60, 60 * 24 * 60)),
            length_seconds=fake.random_int(20, 600),
            prompt_tokens=fake.random_int(500, 5000),
            completion_tokens=fake.random_int(50, 800),
            input_audio_tokens=fake.random_int(500, 15000),
            output_audio_tokens=fake.random_int(500, 15000),
            thinking_tokens=0,
            cached_tokens=fake.random_int(0, 2000),
            cost_usd=Decimal(fake.random_int(100, 9000)) / 100000,
            price_date=now.date(),
        )
    for _ in range(3):
        call_id = fake.hexify("^^^^^^-^^^^^^^^^^")
        bot_ms = fake.random_int(300, 3000)
        CallLog.objects.create(
            call_id=call_id,
            business=business,
            kind="test",
            started_at=now
            - timedelta(
                days=fake.random_int(1, 20)
            ),  # inside the 30 days a log is kept
            events=[
                {"t": 0.0, "call": call_id, "e": "bot_speech", "phase": "start"},
                {
                    "t": bot_ms / 1000,
                    "call": call_id,
                    "e": "barge_in",
                    "bot_speaking": True,
                    "bot_ms": bot_ms,
                },
                {
                    "t": 9.9,
                    "call": call_id,
                    "e": "end",
                    "reason": "cancel",
                    "secs": 9.9,
                    "barge_ins": 1,
                },
            ],
        )
    return business


def seed() -> list[Business]:
    """Makes two Businesses, or nothing when they exist: call logs can't be deleted for 30 days, so a rerun never starts over."""
    database = settings.DATABASES.get("default", {})
    check_local(
        settings.ENVIRONMENT, database.get("HOST", ""), str(database.get("PORT", ""))
    )
    synthetic.fake.seed_instance(259)  # the same data on every run
    synthetic.fake.unique.clear()
    emails = [synthetic.email() for _ in range(2)]
    if Account.objects.filter(email__in=emails).exists():
        return []
    with transaction.atomic():
        made = [a_business(nth, email) for nth, email in enumerate(emails)]
        token, _ = AccessToken.make(made[0], "Claude Code", "full", False)
        module = Module.objects.get(business=made[0])
        changes.stage(token, "remove_module", {"module": module.pk})
    return made


if __name__ == "__main__":
    try:
        made = seed()
    except Refused as why:
        raise SystemExit(f"make seed refused: {why}") from None
    if not made:
        print("Already seeded: nothing to do.")
    for business in made:
        print(f"{business.name}: log in as {business.account.email} / {PASSWORD}")
    if made:
        print(
            f"Set SUPER_ADMIN_EMAIL={made[0].account.email} in .env to see the totals and call logs."
        )
