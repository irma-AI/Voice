"""The Portal stores the core's Call logs, never lets one change, and keeps each until its expiry (make test-db). No mocks of our own code.
The log shape lives once, in contract/call-log.schema.json; the parity tests fail when the Portal, the database or the security rule drifts from it and name the side to edit."""

# pyright: basic
# (django-stubs types model fields for mypy's plugin; strict pyright cannot read them)

import io
import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection, transaction
from django.db.utils import DatabaseError, IntegrityError
from django.test import Client
from jsonschema import Draft202012Validator

from portal.accounts.models import (
    CALL_ID_PATTERN,
    CALL_KINDS,
    Account,
    Business,
    CallLog,
    CallRecord,
)
from tests.portal.helpers import CALL, EVENTS, SECRET, a_call, a_log

pytestmark = [pytest.mark.db, pytest.mark.django_db]

ROOT = Path(__file__).parents[2]
SCHEMA: dict[str, Any] = json.loads(
    (ROOT / "contract/call-log.schema.json").read_text()
)
EVENT: dict[str, Any] = SCHEMA["$defs"]["event"]
LEVELS = EVENTS[4]


@pytest.fixture(autouse=True)
def core_secret(settings: Any) -> None:
    settings.CORE_SECRET = SECRET


def a_business() -> Business:
    account = Account.objects.create_user("user-a@example.com", "x" * 20)
    return Business.objects.create(account=account, name="Owner A's Salon")


def run_sql(*statements: str, params: list[Any] | None = None) -> Any:
    with connection.cursor() as cursor:
        for sql in statements:
            cursor.execute(sql, params)
        return cursor.fetchall() if cursor.description else None


def send(log: Any, secret: str | None = SECRET, raw: bytes | None = None) -> Any:
    headers = {} if secret is None else {"Authorization": f"Bearer {secret}"}
    body = raw if raw is not None else json.dumps(log).encode()
    return Client().post(
        "/api/call-logs/", body, content_type="application/json", headers=headers
    )


def test_a_valid_log_is_stored_and_a_repeat_stores_nothing_more() -> None:
    business = a_business()
    assert send(a_log(business)).status_code == 201
    assert send(a_log(business, events=EVENTS[:1])).status_code == 200
    stored = CallLog.objects.get()
    assert (stored.business, stored.kind, stored.events) == (business, "test", EVENTS)
    assert stored.started_at.isoformat() == "2026-10-19T05:00:00+00:00"


def test_a_log_of_every_kind_the_contract_names_is_stored() -> None:
    """A demo call's log (VOI-243) is stored like the others; the parity test below holds the set to the contract."""
    business = a_business()
    for n, kind in enumerate(CALL_KINDS):
        log = a_log(business, call_id=f"c0ffee-{n:012d}", kind=kind)
        assert send(log).status_code == 201, kind
    assert sorted(CallLog.objects.values_list("kind", flat=True)) == sorted(CALL_KINDS)


# Each bad log is also checked against the schema by the parity test below.
WORDS = [
    {"t": 1.2, "who": "agent", "text": "Hej och välkommen till Frisör Exempel!"},
    {"t": 3.4, "who": "caller", "text": "Vad kostar en klippning?"},
]
BAD: dict[str, dict[str, Any]] = {
    "unknown kind": {"kind": "phone"},
    "words on a call that is not a test call": {"kind": "call_link", "words": WORDS},
    "a word from someone else": {"words": [{"t": 1, "who": "bot", "text": "x"}]},
    "a word with another field": {"words": [{**WORDS[0], "name": "Anna"}]},
    "call id with words": {"call_id": "hello, I would like to book"},
    "time in another zone": {"started_at": "2026-10-19T07:00:00+02:00"},
    "events that are not a list": {"events": {"t": 1}},
    "an event that is not an object": {"events": [1]},
    "an event field the rule does not list": {"events": [{**EVENTS[0], "text": "hej"}]},
    "an event holding words": {
        "events": [{**EVENTS[1], "phase": "jag vill boka en tid"}]
    },
    "a long code": {"events": [{**EVENTS[1], "phase": "x" * 65}]},
    "an event holding a list": {"events": [{**EVENTS[1], "phase": ["hej"]}]},
    "a detector setting holding words": {
        "events": [{**EVENTS[0], "vad": {"start_sensitivity": "very low please"}}]
    },
    "a detector setting holding an object": {
        "events": [{**EVENTS[0], "vad": {"x": {"y": 1}}}]
    },
    "a detector setting with an odd name": {
        "events": [{**EVENTS[0], "vad": {"Start Sensitivity": 1}}]
    },
    "a code holding a NUL": {"events": [{**EVENTS[1], "phase": "a\u0000b"}]},
    "a level trace holding words": {"events": [{**LEVELS, "caller_dbfs": ["hej"]}]},
    "a level trace that is a code": {"events": [{**LEVELS, "bot_dbfs": "loud"}]},
    "a level trace over 20 numbers": {"events": [{**LEVELS, "bot_dbfs": [-20.0] * 21}]},
    "a list in a field that is no trace": {
        "events": [{**EVENTS[2], "echo_corr": [0.9]}]
    },
    "events that are null": {"events": None},
    "a start in the future": {"started_at": "9999-12-31T23:59:59.999999Z"},
}
# What only the database refuses (the schema cannot know the time,
# and only the database ties words to a test call).
DATABASE_ONLY = {"a start in the future", "words on a call that is not a test call"}


@pytest.mark.parametrize("name", sorted(BAD))
def test_a_malformed_log_is_refused_and_stores_nothing(name: str) -> None:
    response = send(a_log(a_business(), **BAD[name]))
    assert response.status_code == 400
    assert CallLog.objects.count() == 0


@pytest.mark.parametrize("name", sorted(BAD))
def test_the_contract_refuses_what_the_portal_refuses(name: str) -> None:
    business = a_business()
    validator = Draft202012Validator(SCHEMA)
    assert not list(validator.iter_errors(a_log(business))), (
        "edit the schema or the example log: a good log must pass"
    )
    if name not in DATABASE_ONLY:
        assert list(validator.iter_errors(a_log(business, **BAD[name]))), (
            f"'{name}' is refused by the Portal but passes the schema: edit contract/call-log.schema.json to refuse it too"
        )


def stored(started_at: datetime) -> CallLog:
    """A log written straight into the table, as any writer could."""
    return CallLog.objects.create(
        call_id=CALL,
        business=a_business(),
        kind="test",
        started_at=started_at,
        events=EVENTS,
    )


def test_a_test_call_s_words_are_stored_and_a_log_without_any_too() -> None:
    business = a_business()
    assert send(a_log(business, words=WORDS)).status_code == 201
    # No words key: any call without words, and a core copy from before VOI-160 still running mid-deploy.
    assert send(a_log(business, call_id="older-core-0001")).status_code == 201
    assert [log.words for log in CallLog.objects.order_by("pk")] == [WORDS, []]


@pytest.mark.parametrize(
    "fields, rule",
    [
        ({"kind": "call_link", "words": WORDS}, "call_log_words_only_on_a_test_call"),
        ({"words": [{"t": 1, "who": "agent"}]}, "call_log_words_hold_only_who_t_text"),
        ({"words": {"t": 1}}, "call_log_words_hold_only_who_t_text"),
        ({"words": [{}]}, "call_log_words_hold_only_who_t_text"),
        (
            {"words": [{"t": 1, "who": None, "text": "x"}]},
            "call_log_words_hold_only_who_t_text",
        ),
    ],
)
def test_the_database_itself_refuses_words_off_a_test_call_or_in_another_shape(
    fields: dict[str, Any], rule: str
) -> None:
    """VOI-160: a bug in the core or any other writer cannot store a real Caller's words."""
    with pytest.raises(IntegrityError, match=rule), transaction.atomic():
        CallLog.objects.create(
            **{
                "call_id": CALL,
                "business": a_business(),
                "kind": "test",
                "started_at": datetime.now(UTC),
                "events": EVENTS,
                **fields,
            }
        )
    assert CallLog.objects.count() == 0


def test_the_database_refuses_an_update_of_a_stored_log() -> None:
    log = stored(datetime.now(UTC) - timedelta(days=40))  # expired, and still final
    refused = "call_log_is_final"
    for sql in (
        "UPDATE accounts_calllog SET events = '[]'",
        "UPDATE accounts_calllog SET kind = 'call_link'",
    ):
        with pytest.raises(DatabaseError, match=refused), transaction.atomic():
            run_sql(sql)
    log.events = []
    with pytest.raises(DatabaseError, match=refused), transaction.atomic():
        log.save()
    assert CallLog.objects.get().events == EVENTS


def test_the_database_refuses_deleting_a_log_before_its_expiry() -> None:
    log = stored(datetime.now(UTC) - timedelta(days=29, hours=23))
    refused = "call_log_is_kept_until_expiry"
    with pytest.raises(DatabaseError, match=refused), transaction.atomic():
        run_sql("DELETE FROM accounts_calllog")
    with pytest.raises(DatabaseError, match=refused), transaction.atomic():
        log.delete()
    assert CallLog.objects.count() == 1


def test_a_log_past_its_expiry_can_be_deleted() -> None:
    stored(datetime.now(UTC) - timedelta(days=30, minutes=1)).delete()
    assert CallLog.objects.count() == 0


def test_the_expiry_command_deletes_only_logs_past_their_expiry_and_no_call_record(
    settings: Any,
) -> None:
    """VOI-157: one minute before expiry kept, one minute after gone; a dry run or a wrong target changes nothing."""
    owner = a_business()
    now = datetime.now(UTC)
    for call_id, age in (
        ("log-kept-000001", timedelta(days=30, minutes=-1)),
        ("log-gone-000001", timedelta(days=30, minutes=1)),
    ):
        CallLog.objects.create(
            call_id=call_id,
            business=owner,
            kind="test",
            started_at=now - age,
            events=EVENTS,
        )
    a_call(owner, "call-old-000001", now - timedelta(days=40))
    settings.ENVIRONMENT = "local"
    with pytest.raises(CommandError, match="--target production"):
        call_command("expire_call_logs", "--target", "production", "--execute")
    out = io.StringIO()
    call_command("expire_call_logs", "--target", "local", stdout=out)
    assert (
        "log-gone-000001" in out.getvalue() and "log-kept-000001" not in out.getvalue()
    )
    assert CallLog.objects.count() == 2  # the dry run deleted nothing
    call_command(
        "expire_call_logs", "--target", "local", "--execute", stdout=io.StringIO()
    )
    assert list(CallLog.objects.values_list("call_id", flat=True)) == [
        "log-kept-000001"
    ]
    assert CallRecord.objects.count() == 1


def test_the_expiry_is_30_days_after_the_call_started() -> None:
    [[expires]] = run_sql(
        "SELECT accounts_call_log_expires_at(%s)",
        params=[datetime(2026, 10, 19, 5, tzinfo=UTC)],
    )
    assert expires == datetime(2026, 11, 18, 5, tzinfo=UTC)


def test_the_expiry_is_the_same_instant_whatever_the_sessions_time_zone() -> None:
    # VOI-261: Stockholm leaves summer time on 2026-10-25, inside these 30 days; a calendar-day expiry came an hour late or early.
    with connection.cursor() as cursor:
        cursor.execute("SET LOCAL TIME ZONE 'Europe/Stockholm'")
        cursor.execute("SHOW TIME ZONE")
        assert cursor.fetchall() == [
            ("Europe/Stockholm",)
        ]  # outside a transaction SET LOCAL would do nothing
        # Compared in SQL: Django's datetime adapters assume a UTC session and would shift both sides.
        cursor.execute(
            "SELECT accounts_call_log_expires_at(timestamptz '2026-10-19 05:00+00')"
            " = timestamptz '2026-11-18 05:00+00'"
        )
        [[exact]] = cursor.fetchall()
    assert exact


def test_a_business_with_logs_cannot_be_deleted() -> None:
    log = stored(datetime.now(UTC))
    with pytest.raises(Exception, match="protected"), transaction.atomic():
        log.business.delete()
    assert Business.objects.count() == 1


def test_the_database_itself_refuses_a_log_that_breaks_a_rule() -> None:
    business = a_business()
    good: dict[str, Any] = {
        "call_id": CALL,
        "business": business,
        "kind": "test",
        "started_at": datetime.now(UTC),
        "events": EVENTS,
    }
    for changes, rule in (
        ({"kind": "phone"}, "call_log_kind"),
        ({"call_id": "words, not a code"}, "call_log_id"),
        (
            {"started_at": datetime.now(UTC) + timedelta(hours=2)},
            "call_log_must_not_start_in_the_future",
        ),
        (
            {"events": [{"t": 1, "text": "hej"}]},
            "call_log_events_hold_only_listed_fields",
        ),
        (
            {"events": [{"t": 1, "src": "hej hej"}]},
            "call_log_events_hold_only_listed_fields",
        ),
        ({"events": {"t": 1}}, "call_log_events_hold_only_listed_fields"),
        (
            {"events": [{"t": 1, "caller_dbfs": ["hej"]}]},
            "call_log_events_hold_only_listed_fields",
        ),
        (
            {"events": [{"t": 1, "bot_dbfs": [-20.0] * 21}]},
            "call_log_events_hold_only_listed_fields",
        ),
        (
            {"events": [{"t": 1, "vad": "low"}]},
            "call_log_events_hold_only_listed_fields",
        ),
        (
            {"events": [{"t": 1, "bot_dbfs": "loud"}]},
            "call_log_events_hold_only_listed_fields",
        ),
        (
            {"events": [{"t": 1, "similarity": [1, 2]}]},
            "call_log_events_hold_only_listed_fields",
        ),
        (  # a user-agent string where the browser family goes
            {
                "events": [
                    {"t": 1, "browser": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0)"}
                ]
            },
            "call_log_events_hold_only_listed_fields",
        ),
        (
            {"events": [{"t": 1, "user_agent": "Safari"}]},
            "call_log_events_hold_only_listed_fields",
        ),
    ):
        with pytest.raises(IntegrityError, match=rule), transaction.atomic():
            CallLog.objects.create(**{**good, **changes})


def security_rule_fields() -> set[str]:
    """The fields `.claude/rules/security.md` lets a production barge-in line hold."""
    rule = (ROOT / ".claude/rules/security.md").read_text()
    line = next(
        line for line in rule.splitlines() if line.startswith("- The barge-in log")
    )
    return set(
        re.findall(r"`([a-z_]+)`", line.split("may hold:", 1)[1].split(". ", 1)[0])
    )


def test_a_stored_event_holds_only_the_fields_the_security_rule_lists() -> None:
    listed = security_rule_fields()
    assert {"t", "call", "e", "secs"} <= listed, (
        "the field list in .claude/rules/security.md was not found"
    )
    assert set(EVENT["properties"]) == listed, (
        "contract/call-log.schema.json's event properties and the barge-in fields in .claude/rules/security.md differ: "
        "add the field to the rule first, then to the schema"
    )
    [[in_store]] = run_sql("SELECT accounts_call_log_fields()")
    assert set(in_store) == listed, (
        "the database's accounts_call_log_fields() and the barge-in fields in .claude/rules/security.md differ: "
        "a new migration redefines the function"
    )
    assert {k for event in EVENTS for k in event} == listed, (
        "give the example events every listed field"
    )


def test_the_log_shape_is_the_same_in_the_schema_and_the_portal() -> None:
    Draft202012Validator.check_schema(SCHEMA)
    names = {f.name for f in CallLog._meta.get_fields() if f.name != "id"}  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType, reportUnknownVariableType]
    # words is the one optional field: the core leaves it out when a call has none (VOI-160).
    assert names == set(SCHEMA["properties"]) == {*SCHEMA["required"], "words"}, (
        "CallLog's fields and the schema's properties and required list must name the same fields: edit whichever is wrong"
    )
    assert set(CALL_KINDS) == set(SCHEMA["properties"]["kind"]["enum"]), (
        "CALL_KINDS in models.py and the schema's kind enum must list the same kinds"
    )
    assert CALL_ID_PATTERN == SCHEMA["properties"]["call_id"]["pattern"], (
        "set the patterns in models.py and the schema to the same text"
    )
