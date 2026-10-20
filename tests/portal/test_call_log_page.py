"""Petter's Call log pages: who may open them, and what they show of a stored log (make test-db). No mocks of our own code."""

# pyright: basic
# (django-stubs types model fields for mypy's plugin; strict pyright cannot read them)

import json
from datetime import UTC, datetime
from typing import Any

import pytest

from portal.accounts.models import Business, CallLog
from tests.portal.helpers import CALL, EVENTS, business_with_login

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
    business_a, client = business_with_login("user-a@example.com", "Owner A's Salon")
    _, petter = business_with_login(EMAIL, "Petter's Business")
    a_log(business_a)  # Owner A's own call: they still see none of it
    settings.SUPER_ADMIN_EMAIL = ""  # unset: nobody, not even the right account
    for page in PAGES:
        assert petter.get(page).status_code == 403
    settings.SUPER_ADMIN_EMAIL = EMAIL
    for page in PAGES:
        assert petter.get(page).status_code == 200
        assert (
            "no-store" in petter.get(page)["Cache-Control"]
        )  # never in a shared cache
        assert client.get(page).status_code == 403
    assert "Call logs for every Business" in petter.get("/dashboard/").content.decode()
    assert (
        "Call logs for every Business" not in client.get("/dashboard/").content.decode()
    )


def test_the_list_sums_up_each_log_on_the_portal_clock(settings: Any) -> None:
    settings.SUPER_ADMIN_EMAIL = EMAIL
    settings.TIME_ZONE = "Europe/Stockholm"  # 05:00 UTC is 07:00 in October
    business_a, _ = business_with_login("user-a@example.com", "Owner A's Salon")
    _, petter = business_with_login(EMAIL, "Petter's Business")
    no_words = {**EVENTS[2], "t": 5.0}  # a second barge-in, no words after it
    a_log(business_a, events=[*EVENTS[:-1], no_words, EVENTS[-1]])
    a_log(
        business_a, call_id="no-end-0000001", events=EVENTS[:3]
    )  # cut short: no end event
    response = petter.get("/logs/")
    page = response.content.decode()
    assert "2026-10-19 07:00" in page and "Owner A&#x27;s Salon · Test call" in page
    assert "2 barge-ins, 1 without words" in page
    assert "1 barge-in, 1 without words" in page
    # Length from the end event's 9.9 s; a log with no end event has none.
    assert sorted(row[4:] for row in response.context["rows"]) == [
        ("0:09", 2, 1),
        ("–", 1, 1),
    ]


def test_the_timeline_shows_every_event_with_its_fields(settings: Any) -> None:
    settings.SUPER_ADMIN_EMAIL = EMAIL
    business_a, _ = business_with_login("user-a@example.com", "Owner A's Salon")
    _, petter = business_with_login(EMAIL, "Petter's Business")
    a_log(business_a, events=[*EVENTS, {"t": 10.0, "call": CALL, "e": "new_kind"}])
    events = petter.get(f"/logs/{CALL}/").context["events"]
    assert [name for _, name, _, _ in events] == [
        "Call starts",
        "Agent speech",
        "Barge-in",
        "Agent speech",
        "Levels around the cut",
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
        "src": "gemini",  # without its JSON quotes; the text file keeps them
        "echo_corr": "0.12",
        "echo_lag_ms": "180",
    }
    # The barge-in has Caller's words after it; start and end are drawn quieter.
    assert [tone for *_, tone in events][:3] == ["frame", "", "barge_in"]
    assert events[-2][3] == "frame"
    assert petter.get("/logs/no-such-call-01/").status_code == 404


def test_a_barge_in_with_no_words_after_it_is_marked_on_its_row(settings: Any) -> None:
    settings.SUPER_ADMIN_EMAIL = EMAIL
    business_a, _ = business_with_login("user-a@example.com", "Owner A's Salon")
    _, petter = business_with_login(EMAIL, "Petter's Business")
    no_words = {**EVENTS[2], "t": 5.0}  # a second barge-in, no words after it
    a_log(business_a, events=[*EVENTS[:-1], no_words, EVENTS[-1]])
    response = petter.get(f"/logs/{CALL}/")
    tones = [tone for *_, tone in response.context["events"]]
    assert tones.count("barge_in") == 1 and tones.count("no_words") == 1
    assert response.content.decode().count("No words after") == 1


def test_the_text_file_has_the_lines_the_core_wrote(settings: Any) -> None:
    settings.SUPER_ADMIN_EMAIL = EMAIL
    business_a, _ = business_with_login("user-a@example.com", "Owner A's Salon")
    _, petter = business_with_login(EMAIL, "Petter's Business")
    a_log(business_a)
    response = petter.get(f"/logs/{CALL}/log.txt")
    assert response["Content-Type"].startswith("text/plain")
    assert f'filename="call-log-{CALL}.txt"' in response["Content-Disposition"]
    lines = response.content.decode().splitlines()
    # The recorder's lines, as voice/bargein.py logs them, character for character; config's vad keeps no key order.
    assert lines[1:] == [f"barge-in {json.dumps(e)}" for e in EVENTS[1:]]
    assert [json.loads(line.removeprefix("barge-in ")) for line in lines] == EVENTS


@pytest.mark.parametrize(
    "events",
    [
        [{"e": "end", "secs": "abc"}],  # a code where a number belongs
        [{"t": 1}],  # no event name
        [{"e": "barge_in"}],  # no time, no call
        [{"call": CALL, "e": "caller_words", "words": 2}],  # words with no barge-in
    ],
)
def test_an_odd_event_the_database_took_never_breaks_the_pages(
    settings: Any, events: Any
) -> None:
    """The database checks an event's field names and value shapes, not that t, call and e are there; one odd log must not take the list down for its 30 days."""
    settings.SUPER_ADMIN_EMAIL = EMAIL
    business_a, _ = business_with_login("user-a@example.com", "Owner A's Salon")
    _, petter = business_with_login(EMAIL, "Petter's Business")
    a_log(business_a, events=events)
    for page in PAGES:
        assert petter.get(page).status_code == 200, page
    length, _, no_words = petter.get("/logs/").context["rows"][0][4:]
    assert length == "–" and no_words >= 0
