"""`make seed` (portal/seed.py): local only, synthetic emails only, and a rerun changes nothing (VOI-259)."""

# pyright: basic

import re
from pathlib import Path

import pytest

from portal import seed, synthetic
from portal.accounts.models import Account, CallLog, CallRecord, PendingChange

pytestmark = [pytest.mark.db, pytest.mark.django_db]


@pytest.mark.parametrize(
    "environment, host, port",
    [
        ("production", "127.0.0.1", "55431"),
        ("local", "portal-db", "55431"),
        ("local", "", "55431"),
        ("local", "127.0.0.1", "5432"),  # a tunnel to someone else's Postgres
    ],
)
def test_the_seed_refuses_anywhere_but_a_local_database(
    environment: str, host: str, port: str
) -> None:
    with pytest.raises(seed.Refused):
        seed.check_local(environment, host, port)
    seed.check_local("local", "127.0.0.1", "55431")  # and lets the local run through


def test_the_seeds_ports_are_the_ones_voices_own_postgres_publishes() -> None:
    published = {
        re.search(r'"127\.0\.0\.1:(\d+):5432"', Path(f).read_text())[1]  # type: ignore[index]
        for f in ("compose.yml", "compose.test.yml")
    }
    assert published == seed.LOCAL_PORTS, "edit LOCAL_PORTS in portal/seed.py"


def test_the_seed_makes_two_businesses_with_reserved_contacts_and_a_rerun_changes_nothing() -> (
    None
):
    made = seed.seed()
    assert len(made) == 2
    assert CallRecord.objects.count() and CallLog.objects.count()
    assert PendingChange.objects.filter(decision="").count() == 1
    assert all(
        email.endswith("@" + synthetic.RESERVED_DOMAIN)
        for email in Account.objects.values_list("email", flat=True)
    )
    assert len(synthetic.RESERVED_PHONES) == 495  # PTS's five series
    for business in made:
        number = re.search(r"\+46\d+", business.instructions)
        assert number and number[0] in synthetic.RESERVED_PHONES
    counts = [m.objects.count() for m in (Account, CallRecord, CallLog)]
    assert seed.seed() == []
    assert [m.objects.count() for m in (Account, CallRecord, CallLog)] == counts
