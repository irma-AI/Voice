"""Seam 2: the call ticket, free. A browser may call for the one Business a Portal ticket names, until it expires."""

import json
from pathlib import Path

import pytest

from voice.ticket import (
    KINDS,
    Ticket,
    frame_ancestors,
    from_query,
    read_ticket,
    sign,
)

SECRET = "s3cret"
NOW = 1_000_000


def good(
    business: int = 7, kind: str = "test", expires: int = NOW + 60, domain: str = ""
) -> str:
    return sign(SECRET, business, kind, expires, domain)


def test_a_signed_unexpired_ticket_names_its_business_kind_and_domain() -> None:
    assert read_ticket(good(), SECRET, NOW) == Ticket(7, "test", "")
    link = good(kind="call_link", domain="shop.example.se")
    assert read_ticket(link, SECRET, NOW) == Ticket(7, "call_link", "shop.example.se")


def test_everything_else_is_refused() -> None:
    mine = good()
    business, kind, expires, domain, signature = mine.split(".")
    for bad in (
        None,
        "",
        "7",
        "7.1",
        "7.1.abc",  # the old three-part spelling, without a kind
        f"{business}.{kind}.{expires}.{signature}",  # the old four-part spelling, without a domain
        mine + "0",  # signature too long
        f"8.{kind}.{expires}.{domain}.{signature}",  # another Business with this one's signature
        f"{business}.call_link.{expires}.{domain}.{signature}",  # another kind with this one's signature
        f"{business}.{kind}.{NOW + 9999}.{domain}.{signature}",  # a longer life with this one's signature
        f"{business}.{kind}.{expires}.{domain}.{signature[:-1]}",
        f"{business}.{kind}.{expires}.{domain}.é{signature[1:]}",  # not ASCII: refused, not a crash
        f"٧.{kind}.{expires}.{domain}.{signature}",  # a non-ASCII digit
        sign("other", 7, "test", NOW + 60),  # signed with another secret
        sign(SECRET, 7, "phone", NOW + 60),  # signed, but not a kind the core knows
        good(expires=NOW - 1),  # expired
        f"-7.{kind}.{expires}.{domain}.{signature}",
        f"0{business}.{kind}.{expires}.{domain}.{signature}",  # not written the one way sign() writes it
        f"1.{kind}.{'9' * 5000}.{domain}.{signature}",  # too many digits for int(): refused, not an error
        f"{'9' * 5000}.{kind}.{expires}.{domain}.{signature}",
    ):
        assert read_ticket(bad, SECRET, NOW) is None, bad


def test_a_call_link_ticket_needs_a_plain_hostname_and_a_test_call_has_none() -> None:
    for domain in (
        "",  # no saved domain
        "example",  # one label
        "exa mple.se",
        "example.se;",  # would end a header value
        "https://example.se",
        "example.se/path",
        "*.example.se",
        "Example.se",
        "example.se\n",
        "-example.se",
        "a." * 200 + "se",  # longer than a hostname can be
    ):
        assert (
            read_ticket(good(kind="call_link", domain=domain), SECRET, NOW) is None
        ), domain
    assert read_ticket(good(kind="test", domain="example.se"), SECRET, NOW) is None
    # A demo call is framed by the landing page, so it carries a domain like a call link.
    assert read_ticket(good(kind="demo", domain=""), SECRET, NOW) is None
    assert read_ticket(good(kind="demo", domain="example.se"), SECRET, NOW) == Ticket(
        7, "demo", "example.se"
    )


def test_a_hostname_may_be_253_characters_and_no_longer() -> None:
    longest = "a" * 63 + (".") + "a" * 63 + "." + "a" * 63 + "." + "a" * 58 + ".se"
    assert len(longest) == 253
    assert read_ticket(good(kind="call_link", domain=longest), SECRET, NOW)
    assert (
        read_ticket(good(kind="call_link", domain="a" + longest), SECRET, NOW) is None
    )


def test_the_call_page_may_be_framed_only_by_the_businesss_own_site() -> None:
    assert (
        frame_ancestors("example.se")
        == "frame-ancestors https://example.se https://*.example.se"
    )
    assert frame_ancestors("") == "frame-ancestors 'none'"  # a test call: nobody
    for bad in ("exa mple.se", "example.se;", "https://example.se", "*.example.se"):
        with pytest.raises(ValueError):
            frame_ancestors(bad)  # never written into a header


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
