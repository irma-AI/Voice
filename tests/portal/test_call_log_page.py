"""Petter's Call log pages: who may open them, and what they show of a stored log (make test-db). No mocks of our own code."""

# pyright: basic
# (django-stubs types model fields for mypy's plugin; strict pyright cannot read them)

import json
from datetime import UTC, datetime
from typing import Any

import pytest
from django.test import Client

from portal.accounts.models import Business, CallLog
from tests.portal.helpers import business_with_login
from tests.portal.test_call_logs import CALL, EVENTS

pytestmark = [pytest.mark.db, pytest.mark.django_db]

EMAIL = "petter.testsson@example.com"  # synthetic
PAGES = [f"/logs/{CALL}/", f"/logs/{CALL}/log.txt", "/logs/"]


def a_log(owner: Business, call_id: str = CALL, events: Any = EVENTS) -> None:
    """Made by hand, the way record_call_log stores what the core sends."""
    CallLog.objects.create(
        call_id=call_id,
        business=owner,
        kind="test",
        started_at=datetime(2026, 10, 19, 5, 0, tzinfo=UTC),
        events=events,
    )


def test_only_the_operator_opens_the_pages_and_a_visitor_goes_to_the_login(
    settings: Any,
) -> None:
    anna, client = business_with_login("anna.testsson@example.com", "Anna's Salon")
    _, petter = business_with_login(EMAIL, "Petter's Business")
    a_log(anna)  # Anna's own call: she still sees none of it
    settings.SUPER_ADMIN_EMAIL = ""  # unset: nobody, not even the right account
    for page in PAGES:
        assert petter.get(page).status_code == 403
    settings.SUPER_ADMIN_EMAIL = EMAIL
    for page in PAGES:
        assert petter.get(page).status_code == 200
        assert client.get(page).status_code == 403
        assert Client().get(page)["Location"].startswith("/login/")
    assert "Call logs for every Business" in petter.get("/dashboard/").content.decode()
    assert (
        "Call logs for every Business" not in client.get("/dashboard/").content.decode()
    )


def test_the_list_sums_up_each_log_on_the_portal_clock(settings: Any) -> None:
    settings.SUPER_ADMIN_EMAIL = EMAIL
    settings.TIME_ZONE = "Europe/Stockholm"  # 05:00 UTC is 07:00 in October
    anna, _ = business_with_login("anna.testsson@example.com", "Anna's Salon")
    _, petter = business_with_login(EMAIL, "Petter's Business")
    no_words = {**EVENTS[2], "t": 5.0}  # a second barge-in, no words after it
    a_log(anna, events=[*EVENTS[:-1], no_words, EVENTS[-1]])
    a_log(anna, call_id="no-end-0000001", events=EVENTS[:3])  # cut short: no end event
    response = petter.get("/logs/")
    page = response.content.decode()
    assert "2026-10-19 07:00" in page and "Anna&#x27;s Salon · Test call" in page
    assert "2 barge-ins, 1 without words" in page
    assert "1 barge-in, 1 without words" in page
    # Length from the end event's 9.9 s; a log with no end event has none.
    assert sorted(row[4:] for row in response.context["rows"]) == [
        ("0:09", 2, 1),
        ("–", 1, 1),
    ]


def test_the_timeline_shows_every_event_with_its_fields(settings: Any) -> None:
    settings.SUPER_ADMIN_EMAIL = EMAIL
    anna, _ = business_with_login("anna.testsson@example.com", "Anna's Salon")
    _, petter = business_with_login(EMAIL, "Petter's Business")
    a_log(anna, events=[*EVENTS, {"t": 10.0, "call": CALL, "e": "new_kind"}])
    events = petter.get(f"/logs/{CALL}/").context["events"]
    assert [name for _, name, _ in events] == [
        "Call starts",
        "Agent speech",
        "Barge-in",
        "Agent speech",
        "Caller's words",
        "Agent resumes",
        "Call ends",
        "new_kind",  # an event the page has no name for still shows, by its code
    ]
    barge_in = dict(events[2][2])
    assert barge_in == {
        "bot_speaking": "true",
        "bot_ms": "1300",
        "peak_dbfs": "-12.5",
        "rms_dbfs": "-30.1",
        "src": '"gemini"',
    }
    assert petter.get("/logs/no-such-call-01/").status_code == 404


def test_the_text_file_has_the_lines_the_core_wrote(settings: Any) -> None:
    settings.SUPER_ADMIN_EMAIL = EMAIL
    anna, _ = business_with_login("anna.testsson@example.com", "Anna's Salon")
    _, petter = business_with_login(EMAIL, "Petter's Business")
    a_log(anna)
    response = petter.get(f"/logs/{CALL}/log.txt")
    assert response["Content-Type"].startswith("text/plain")
    assert f'filename="call-log-{CALL}.txt"' in response["Content-Disposition"]
    lines = response.content.decode().splitlines()
    # The recorder's line, as voice/bargein.py logs it: the prefix and the event's JSON, t, call and e first.
    assert lines[2].startswith(
        'barge-in {"t": 2.5, "call": "' + CALL + '", "e": "barge_in"'
    )
    assert [json.loads(line.removeprefix("barge-in ")) for line in lines] == EVENTS
