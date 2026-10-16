"""Seam 2: the call ticket, free. A browser may call for the one Business a Portal ticket names, until it expires."""

from voice.ticket import from_query, sign, ticket_business

SECRET = "s3cret"
NOW = 1_000_000


def good(business: int = 7, expires: int = NOW + 60) -> str:
    return sign(SECRET, business, expires)


def test_a_signed_unexpired_ticket_names_its_business() -> None:
    assert ticket_business(good(), SECRET, NOW) == 7


def test_everything_else_is_refused() -> None:
    mine = good()
    business, expires, signature = mine.split(".")
    for bad in (
        None,
        "",
        "7",
        "7.1",
        mine + "0",  # signature too long
        f"8.{expires}.{signature}",  # another Business with this one's signature
        f"{business}.{NOW + 9999}.{signature}",  # a longer life with this one's signature
        f"{business}.{expires}.{signature[:-1]}",
        f"{business}.{expires}.é{signature[1:]}",  # not ASCII: refused, not a crash
        f"٧.{expires}.{signature}",  # a non-ASCII digit
        sign("other", 7, NOW + 60),  # signed with another secret
        good(expires=NOW - 1),  # expired
        f"-7.{expires}.{signature}",
        f"0{business}.{expires}.{signature}",  # not written the one way sign() writes it
        f"1.{'9' * 5000}.{signature}",  # too many digits for int(): refused, not an error
        f"{'9' * 5000}.{expires}.{signature}",
    ):
        assert ticket_business(bad, SECRET, NOW) is None, bad


def test_no_secret_means_no_ticket_is_ever_valid() -> None:
    assert ticket_business(sign("", 7, NOW + 60), "", NOW) is None


def test_the_ticket_is_read_from_the_query_string() -> None:
    assert from_query(b"ticket=7.1.abc") == "7.1.abc"
    assert from_query(b"x=1&ticket=7.1.abc&ticket=other") == "7.1.abc"
    assert from_query(b"") is None
