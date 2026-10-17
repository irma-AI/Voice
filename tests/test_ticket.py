"""Seam 2: the call ticket, free. A browser may call for the one Business a Portal ticket names, until it expires."""

import json
from pathlib import Path

from voice.ticket import KINDS, Ticket, from_query, read_ticket, sign

SECRET = "s3cret"
NOW = 1_000_000


def good(business: int = 7, kind: str = "test", expires: int = NOW + 60) -> str:
    return sign(SECRET, business, kind, expires)


def test_a_signed_unexpired_ticket_names_its_business_and_kind() -> None:
    assert read_ticket(good(), SECRET, NOW) == Ticket(7, "test")
    assert read_ticket(good(kind="call_link"), SECRET, NOW) == Ticket(7, "call_link")


def test_everything_else_is_refused() -> None:
    mine = good()
    business, kind, expires, signature = mine.split(".")
    for bad in (
        None,
        "",
        "7",
        "7.1",
        "7.1.abc",  # the old three-part spelling, without a kind
        mine + "0",  # signature too long
        f"8.{kind}.{expires}.{signature}",  # another Business with this one's signature
        f"{business}.call_link.{expires}.{signature}",  # another kind with this one's signature
        f"{business}.{kind}.{NOW + 9999}.{signature}",  # a longer life with this one's signature
        f"{business}.{kind}.{expires}.{signature[:-1]}",
        f"{business}.{kind}.{expires}.é{signature[1:]}",  # not ASCII: refused, not a crash
        f"٧.{kind}.{expires}.{signature}",  # a non-ASCII digit
        sign("other", 7, "test", NOW + 60),  # signed with another secret
        sign(SECRET, 7, "phone", NOW + 60),  # signed, but not a kind the core knows
        good(expires=NOW - 1),  # expired
        f"-7.{kind}.{expires}.{signature}",
        f"0{business}.{kind}.{expires}.{signature}",  # not written the one way sign() writes it
        f"1.{kind}.{'9' * 5000}.{signature}",  # too many digits for int(): refused, not an error
        f"{'9' * 5000}.{kind}.{expires}.{signature}",
    ):
        assert read_ticket(bad, SECRET, NOW) is None, bad


def test_no_secret_means_no_ticket_is_ever_valid() -> None:
    assert read_ticket(sign("", 7, "test", NOW + 60), "", NOW) is None


def test_the_ticket_is_read_from_the_query_string() -> None:
    assert from_query(b"ticket=7.1.abc") == "7.1.abc"
    assert from_query(b"x=1&ticket=7.1.abc&ticket=other") == "7.1.abc"
    assert from_query(b"") is None


def test_the_core_knows_the_kinds_the_contract_names() -> None:
    """A new kind is added to voice/ticket.py KINDS and the contract together (the Portal's CALL_KINDS is held to the contract by tests/portal/test_call_records.py)."""
    schema = json.loads(
        (Path(__file__).parents[1] / "contract/call-record.schema.json").read_text()
    )
    assert set(KINDS) == set(schema["properties"]["kind"]["enum"])
