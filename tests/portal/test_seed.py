"""`make seed` (portal/seed.py): local only, synthetic emails only, and a rerun changes nothing (VOI-259)."""

# pyright: basic

import re

import pytest

from portal import seed, synthetic
from portal.accounts.models import Account, CallLog, CallRecord, PendingChange

pytestmark = [pytest.mark.db, pytest.mark.django_db]


@pytest.mark.parametrize(
    "environment, host",
    [("production", "127.0.0.1"), ("local", "portal-db"), ("local", "")],
)
def test_the_seed_refuses_anywhere_but_a_local_database(
    environment: str, host: str
) -> None:
    with pytest.raises(seed.Refused):
        seed.check_local(environment, host)
    seed.check_local("local", "127.0.0.1")  # and lets the local run through


def test_the_seed_fills_every_page_with_reserved_emails_and_a_rerun_changes_nothing() -> (
    None
):
    made = seed.seed()
    assert len(made) == 2
    assert CallRecord.objects.count() and CallLog.objects.count()
    assert PendingChange.objects.filter(decision="").count() == 1
    assert all(
        email.rsplit("@", 1)[1] in synthetic.RESERVED_DOMAINS
        for email in Account.objects.values_list("email", flat=True)
    )
    assert len(synthetic.RESERVED_PHONES) == 495  # PTS's five series
    for business in made:
        number = re.search(r"\+46\d+", business.instructions)
        assert number and number[0] in synthetic.RESERVED_PHONES
    counts = [m.objects.count() for m in (Account, CallRecord, CallLog)]
    assert seed.seed() == []
    assert [m.objects.count() for m in (Account, CallRecord, CallLog)] == counts
