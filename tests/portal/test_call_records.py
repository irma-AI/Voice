"""The Portal stores the core's Call records and the database never lets one change (make test-db). No mocks of our own code.
The record shape lives once, in contract/call-record.schema.json; the parity tests fail when the Portal drifts from it and name the side to edit."""

# pyright: basic
# (django-stubs types model fields for mypy's plugin; strict pyright cannot read them)

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from django.db import connection, transaction
from django.db.utils import DatabaseError, IntegrityError
from django.test import Client
from jsonschema import Draft202012Validator

from portal.accounts.models import (
    CALL_ID_PATTERN,
    CALL_KINDS,
    COST_REASON_PATTERN,
    Account,
    Business,
    CallRecord,
)

pytestmark = [pytest.mark.db, pytest.mark.django_db]

SECRET = "a-secret-for-tests"
SCHEMA: dict[str, Any] = json.loads(
    (Path(__file__).parents[2] / "contract/call-record.schema.json").read_text()
)
PROPERTIES: dict[str, Any] = SCHEMA["properties"]


@pytest.fixture(autouse=True)
def core_secret(settings: Any) -> None:
    settings.CORE_SECRET = SECRET


def a_business() -> Business:
    account = Account.objects.create_user("anna.testsson@example.com", "x" * 20)
    return Business.objects.create(account=account, name="Anna's Salon")


def a_record(owner: Business, **changes: Any) -> dict[str, Any]:
    return {
        "call_id": "c0ffee-0123456789",
        "business": owner.pk,
        "kind": "call_link",
        "started_at": "2026-10-17T05:00:00Z",
        "length_seconds": 184,
        "prompt_tokens": 1200,
        "completion_tokens": 340,
        "input_audio_tokens": 4600,
        "output_audio_tokens": 3100,
        "thinking_tokens": 0,
        "cached_tokens": 800,
        "cost_usd": "0.01234567",
        "price_date": "2026-10-17",
        "cost_reason": None,
        **changes,
    }


def run_sql(*statements: str) -> None:
    with connection.cursor() as cursor:
        for sql in statements:
            cursor.execute(sql)


def send(record: Any, secret: str | None = SECRET, raw: bytes | None = None) -> Any:
    headers = {} if secret is None else {"Authorization": f"Bearer {secret}"}
    body = raw if raw is not None else json.dumps(record).encode()
    return Client().post(
        "/api/calls/", body, content_type="application/json", headers=headers
    )


def test_a_valid_record_is_stored_and_a_repeat_stores_nothing_more() -> None:
    record = a_record(a_business())
    assert send(record).status_code == 201
    assert send(record).status_code == 200
    stored = CallRecord.objects.get()
    assert (stored.kind, stored.length_seconds, str(stored.cost_usd)) == (
        "call_link",
        184,
        "0.01234567",
    )
    assert stored.started_at.isoformat() == "2026-10-17T05:00:00+00:00"


def test_a_record_with_no_cost_keeps_its_length_and_tokens_and_says_why() -> None:
    record = a_record(
        a_business(),
        cost_usd=None,
        price_date=None,
        cost_reason="catalogue_unreachable",
    )
    assert send(record).status_code == 201
    stored = CallRecord.objects.get()
    assert (stored.cost_usd, stored.cost_reason, stored.prompt_tokens) == (
        None,
        "catalogue_unreachable",
        1200,
    )


def test_without_the_secret_or_with_a_wrong_one_it_answers_401_before_any_lookup(
    django_assert_num_queries: Any, settings: Any
) -> None:
    record = a_record(a_business())
    with django_assert_num_queries(0):
        assert send(record, secret=None).status_code == 401
        assert send(record, secret="wrong").status_code == 401
        assert send({}, secret="wrong").status_code == 401  # not even read
    settings.CORE_SECRET = ""
    assert send(record, secret="").status_code == 401  # an unset secret refuses all
    assert CallRecord.objects.count() == 0


def test_only_a_post_is_answered() -> None:
    assert (
        Client()
        .get("/api/calls/", headers={"Authorization": f"Bearer {SECRET}"})
        .status_code
        == 405
    )


def test_a_record_for_an_unknown_business_is_refused() -> None:
    business = a_business()
    response = send(a_record(business, business=business.pk + 1))
    assert response.status_code == 400 and response.json()["fields"] == ["business"]
    assert CallRecord.objects.count() == 0


# Each bad record is also checked against the schema by the parity test below.
BAD: dict[str, dict[str, Any]] = {
    "unknown kind": {"kind": "demo"},
    "negative length": {"length_seconds": -1},
    "negative tokens": {"thinking_tokens": -5},
    "fractional tokens": {"prompt_tokens": 1.5},
    "call id with words": {"call_id": "hello, I would like to book"},
    "call id too short": {"call_id": "abc"},
    "time with no UTC mark": {"started_at": "2026-10-17T05:00:00"},
    "time in another zone": {"started_at": "2026-10-17T07:00:00+02:00"},
    "time that is not real": {"started_at": "2026-13-45T05:00:00Z"},
    "date in another spelling": {"price_date": "10/17/2026"},
    "negative cost": {"cost_usd": "-0.5"},
    "cost with a currency": {"cost_usd": "12 kr"},
    "cost with no price date": {"price_date": None},
    "cost and a reason": {"cost_reason": "catalogue_unreachable"},
    "no cost and no reason": {"cost_usd": None, "price_date": None},
    "reason that is a sentence": {
        "cost_usd": None,
        "price_date": None,
        "cost_reason": "The catalogue was down",
    },
    "business that is not a number": {"business": "abc"},
    "a start in the future": {"started_at": "9999-12-31T23:59:59Z"},
}


@pytest.mark.parametrize("name", sorted(BAD))
def test_a_malformed_record_is_refused_and_stores_nothing(name: str) -> None:
    record = a_record(a_business(), **BAD[name])
    assert send(record).status_code == 400
    assert CallRecord.objects.count() == 0


@pytest.mark.parametrize("name", sorted(BAD))
def test_the_contract_refuses_what_the_portal_refuses(name: str) -> None:
    business = a_business()
    validator = Draft202012Validator(SCHEMA)
    assert not list(validator.iter_errors(a_record(business))), (
        "edit the schema or the example record: a good record must pass"
    )
    # "no cost and a reason of the wrong kind" and similar rules are the database's, not the schema's.
    database_only = {
        "cost with no price date",
        "cost and a reason",
        "no cost and no reason",
        "business that is not a number",
        "time that is not real",
        "unknown kind",
        "a start in the future",  # the schema cannot know the time
    }
    if name not in database_only:
        assert list(validator.iter_errors(a_record(business, **BAD[name]))), (
            f"'{name}' is refused by the Portal but passes the schema: edit contract/call-record.schema.json to refuse it too"
        )


def test_only_the_listed_fields_are_accepted_and_all_are_required() -> None:
    business = a_business()
    assert send(a_record(business, note="hello")).status_code == 400
    assert send(a_record(business, transcript="hello")).status_code == 400
    record = a_record(business)
    del record["cost_reason"]
    assert send(record).status_code == 400
    assert send(None, raw=b"not json").status_code == 400
    assert send([1, 2]).status_code == 400
    assert CallRecord.objects.count() == 0


def test_the_database_refuses_update_and_delete_of_a_stored_record() -> None:
    business = a_business()
    send(a_record(business))
    record = CallRecord.objects.get()
    refused = "call_record_is_final"
    run_sql(
        "SET CONSTRAINTS ALL IMMEDIATE"
    )  # no pending key checks to hide the refusal
    for sql in (
        "UPDATE accounts_callrecord SET length_seconds = 1",
        "DELETE FROM accounts_callrecord",
    ):
        with pytest.raises(DatabaseError, match=refused), transaction.atomic():
            run_sql(sql)
    record.length_seconds = 1
    with pytest.raises(DatabaseError, match=refused), transaction.atomic():
        record.save()
    with pytest.raises(DatabaseError, match=refused), transaction.atomic():
        record.delete()
    assert CallRecord.objects.get().length_seconds == 184


def test_a_business_with_records_cannot_be_deleted() -> None:
    business = a_business()
    send(a_record(business))
    with pytest.raises(Exception, match="protected"), transaction.atomic():
        business.delete()  # the application's way
    with pytest.raises(IntegrityError), transaction.atomic():
        # whatever else holds a connection; Django's keys check at commit, so ask for it now
        run_sql("SET CONSTRAINTS ALL IMMEDIATE", "DELETE FROM accounts_business")
    assert Business.objects.count() == 1


def test_the_database_itself_refuses_a_record_that_breaks_a_rule() -> None:
    business = a_business()
    good: dict[str, Any] = {
        k: v for k, v in a_record(business).items() if k != "cost_usd"
    }
    good.update(
        business_id=good.pop("business"), cost_usd=None, price_date=None, cost_reason=""
    )
    with (
        pytest.raises(IntegrityError, match="call_record_has_a_cost"),
        transaction.atomic(),
    ):
        CallRecord.objects.create(**good)  # no cost and no reason
    with pytest.raises(IntegrityError, match="call_record_kind"), transaction.atomic():
        CallRecord.objects.create(**{**good, "kind": "demo", "cost_reason": "none_yet"})
    with pytest.raises(IntegrityError, match="call_record_id"), transaction.atomic():
        CallRecord.objects.create(
            **{**good, "call_id": "words, not a code", "cost_reason": "none_yet"}
        )
    with (
        pytest.raises(IntegrityError, match="call_record_must_not_start_in_the_future"),
        transaction.atomic(),
    ):
        CallRecord.objects.create(
            **{
                **good,
                "started_at": datetime.now(UTC) + timedelta(hours=2),
                "cost_reason": "none_yet",
            }
        )
    # Within the hour the core's clock may run ahead.
    CallRecord.objects.create(
        **{
            **good,
            "started_at": datetime.now(UTC) + timedelta(minutes=30),
            "cost_reason": "none_yet",
        }
    )


def test_the_record_shape_is_the_same_in_the_schema_and_the_portal() -> None:
    Draft202012Validator.check_schema(SCHEMA)
    names = {f.name for f in CallRecord._meta.get_fields() if f.name != "id"}  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType, reportUnknownVariableType]
    assert names == set(PROPERTIES) == set(SCHEMA["required"]), (
        "CallRecord's fields and the schema's properties and required list must name the same fields: edit whichever is wrong"
    )
    assert set(CALL_KINDS) == set(PROPERTIES["kind"]["enum"]), (
        "CALL_KINDS in models.py and the schema's kind enum must list the same kinds"
    )
    assert (CALL_ID_PATTERN, COST_REASON_PATTERN) == (
        PROPERTIES["call_id"]["pattern"],
        PROPERTIES["cost_reason"]["pattern"],
    ), "set the patterns in models.py and the schema to the same text"
    assert CallRecord._meta.get_field("call_id").max_length == 64  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
