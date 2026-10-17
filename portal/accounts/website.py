"""The website addresses a Business lists for its call button (VOI-31): what an address may be, and how many.

An address is a browser's `Origin` for a page: https, a host, an optional port, nothing else. The button only starts a
call when the page's Origin is in the list, compared as plain text (views.py `call_from_site`). The database refuses
anything else (migration 0006 holds a copy of the pattern and the limit; tests/portal/test_call_button.py reads both and fails naming the side to edit).
"""

import re
from urllib.parse import urlsplit

ADDRESSES_MAX = 5
ORIGIN_MAX = 300  # the column Business.website_addresses holds
# Lower case, no trailing dot, no wildcard, no path: what a browser writes in `Origin` for a https page.
ORIGIN_PATTERN = r"^https://[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*(:[0-9]{1,5})?$"

PLAIN = "Write only the website's address, like https://example.se, one per line."


def parse_origin(line: str) -> str:
    """The `Origin` a typed website address means, in the spelling a browser sends it; raises ValueError with the sentence to show."""
    bad = ValueError(f"{line.strip()!r} is not usable. {PLAIN}")
    parts = urlsplit(line.strip())
    # A trailing "/" is what people paste; anything after it is a page, which an Origin never has.
    if (
        parts.scheme.lower() != "https"
        or not parts.hostname
        or parts.path not in ("", "/")
        or parts.query
        or parts.fragment
        or "@" in parts.netloc
        or "*" in parts.netloc
    ):
        raise bad
    try:
        host = parts.hostname.encode("idna").decode()  # åäö domains: browsers send xn--
        port = parts.port
        # Python's codec is IDNA 2003: it silently rewrites ß, ς and invisible characters, where a browser sends another
        # name. A typed name that does not survive the round trip is refused, so the stored name is always the typed one.
        if (
            not parts.hostname.isascii()
            and host.encode().decode("idna") != parts.hostname
        ):
            raise bad
    except (UnicodeError, ValueError):
        raise bad from None
    origin = f"https://{host}" + (f":{port}" if port not in (None, 443) else "")
    if len(origin) > ORIGIN_MAX or not re.fullmatch(ORIGIN_PATTERN, origin):
        raise bad
    return origin


def parse_addresses(text: str) -> list[str]:
    """The list a typed box means: one address per line, blank lines ignored, repeats dropped; raises ValueError with the sentence to show."""
    found: list[str] = []
    for line in text.splitlines():
        if line.strip() and (origin := parse_origin(line)) not in found:
            found.append(origin)
    if len(found) > ADDRESSES_MAX:
        raise ValueError(f"List at most {ADDRESSES_MAX} websites.")
    return found
