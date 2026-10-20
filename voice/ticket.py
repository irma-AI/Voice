"""The call ticket: how the Portal tells the core which Business a browser may call for.

The Portal signs `<business id>.<kind>.<expiry>.<domain>` with the shared CORE_SECRET when a Business's test call button
or call link sends a browser here; the core checks it here before it opens a model session, and the kind goes on the
Call record (VOI-41). The domain is the Business's saved website (VOI-71): a call link names it, a test call has none,
and the call page lets only that site frame it. portal/accounts/ticket.py signs the same
way (neither imports the other, ADR 0002): tests/portal/test_test_call.py mints with that and checks with this,
and fails naming the side to edit.
"""

import hashlib
import hmac
import re
import time
from typing import NamedTuple
from urllib.parse import parse_qs

# Where the call came from; contract/call-record.schema.json lists the same four (tests/test_ticket.py fails when they differ).
# A demo call is a visitor's call from the landing page, capped shorter (voice/serve.py CALL_SECS); nothing mints one yet (VOI-243).
# An agent test call is a test call from a link a Business's AI assistant asked for: it counts toward the daily budget (VOI-115).
KINDS = ("test", "call_link", "demo", "agent_test")
# The kinds framed by nobody, so their tickets carry no domain.
UNFRAMED = ("test", "agent_test")
# The label keeps a ticket's signature from being reused as anything else the secret signs.
LABEL = b"call-ticket:"
# A plain lower-case hostname of two labels or more, as the Portal stores it (portal/accounts/domain.py DOMAIN_PATTERN;
# tests/portal/test_call_link.py fails naming the side to edit when they differ). It goes into a response header, so nothing else may.
DOMAIN_PATTERN = (
    r"^([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$"
)
DOMAIN_MAX = 253


class Ticket(NamedTuple):
    business: int
    kind: str
    domain: str = ""


def is_clean_domain(domain: str) -> bool:
    return (
        len(domain) <= DOMAIN_MAX and re.fullmatch(DOMAIN_PATTERN, domain) is not None
    )


def frame_ancestors(domain: str) -> str:
    """The Content-Security-Policy that lets only the Business's own website (and its subdomains) frame the call page; no domain means no frame at all.

    Raises ValueError for a domain that is not a plain hostname, so nothing odd is ever written into a header.
    """
    if not domain:
        return "frame-ancestors 'none'"
    if not is_clean_domain(domain):
        raise ValueError("not a plain hostname")
    return f"frame-ancestors https://{domain} https://*.{domain}"


def sign(
    secret: str, business_id: int, kind: str, expires: int, domain: str = ""
) -> str:
    """`<business id>.<kind>.<expiry, unix seconds>.<domain>.<signature>`: digits, lower case, hex, hyphens and dots only, so it is safe in an address."""
    body = f"{business_id}.{kind}.{expires}.{domain}"
    mac = hmac.new(secret.encode(), LABEL + body.encode(), hashlib.sha256)
    return f"{body}.{mac.hexdigest()}"


def read_ticket(
    ticket: str | None, secret: str, now: float | None = None
) -> Ticket | None:
    """The Business and kind a valid, unexpired ticket is for, else None. No secret set means no ticket is ever valid."""
    if not ticket or not secret:
        return None
    business, _, rest = ticket.partition(".")
    kind, _, rest = rest.partition(".")
    expires, _, rest = rest.partition(".")
    domain, dot, signature = rest.rpartition(
        "."
    )  # a domain has dots; the signature has none
    if not dot or kind not in KINDS:
        return None
    # A test call is framed by nobody, so it carries no domain; a call link or demo call carries the one site that may frame it.
    if (kind in UNFRAMED and domain) or (
        kind not in UNFRAMED and not is_clean_domain(domain)
    ):
        return None
    for part in (business, expires):
        # Short ASCII digits written the one way sign() writes them; int() raises on thousands of digits, so length first.
        if not (part.isascii() and part.isdigit() and len(part) <= 18):
            return None
        if part != str(int(part)):
            return None
    wanted = sign(secret, int(business), kind, int(expires), domain).rpartition(".")[2]
    if not hmac.compare_digest(signature.encode(), wanted.encode()):
        return None
    if int(expires) < (time.time() if now is None else now):
        return None
    return Ticket(int(business), kind, domain)


def from_query(query: bytes) -> str | None:
    """The ticket in a request's query string (`?ticket=...`), if any: the first one, and a blank one counts, so it is refused."""
    values = parse_qs(query.decode("latin-1"), keep_blank_values=True).get("ticket")
    return values[0] if values else None
