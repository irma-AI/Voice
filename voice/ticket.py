"""The call ticket: how the Portal tells the core which Business a browser may call for.

The Portal signs `<business id>.<kind>.<expiry>` with the shared CORE_SECRET when a Business's test call button or
call link sends a browser here; the core checks it here before it opens a model session, and the kind goes on the
Call record (VOI-41). portal/accounts/ticket.py signs the same
way (neither imports the other, ADR 0002): tests/portal/test_test_call.py mints with that and checks with this,
and fails naming the side to edit.
"""

import hashlib
import hmac
import time
from typing import NamedTuple
from urllib.parse import parse_qs

# Where the call came from; contract/call-record.schema.json lists the same two (tests/test_ticket.py fails when they differ).
KINDS = ("test", "call_link")
# The label keeps a ticket's signature from being reused as anything else the secret signs.
LABEL = b"call-ticket:"


class Ticket(NamedTuple):
    business: int
    kind: str


def sign(secret: str, business_id: int, kind: str, expires: int) -> str:
    """`<business id>.<kind>.<expiry, unix seconds>.<signature>`: digits, lower case, hex and dots only, so it is safe in an address."""
    body = f"{business_id}.{kind}.{expires}"
    mac = hmac.new(secret.encode(), LABEL + body.encode(), hashlib.sha256)
    return f"{body}.{mac.hexdigest()}"


def read_ticket(
    ticket: str | None, secret: str, now: float | None = None
) -> Ticket | None:
    """The Business and kind a valid, unexpired ticket is for, else None. No secret set means no ticket is ever valid."""
    if not ticket or not secret:
        return None
    parts = ticket.split(".")
    if len(parts) != 4:
        return None
    business, kind, expires, signature = parts
    if kind not in KINDS:
        return None
    for part in (business, expires):
        # Short ASCII digits written the one way sign() writes them; int() raises on thousands of digits, so length first.
        if not (part.isascii() and part.isdigit() and len(part) <= 18):
            return None
        if part != str(int(part)):
            return None
    wanted = sign(secret, int(business), kind, int(expires)).rpartition(".")[2]
    if not hmac.compare_digest(signature.encode(), wanted.encode()):
        return None
    if int(expires) < (time.time() if now is None else now):
        return None
    return Ticket(int(business), kind)


def from_query(query: bytes) -> str | None:
    """The ticket in a request's query string (`?ticket=...`), if any: the first one, and a blank one counts, so it is refused."""
    values = parse_qs(query.decode("latin-1"), keep_blank_values=True).get("ticket")
    return values[0] if values else None
