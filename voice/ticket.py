"""The call ticket: how the Portal tells the core which Business a browser may call for.

The Portal signs `<business id>.<expiry>` with the shared CORE_SECRET when a logged-in Business presses its test
call button; the core checks it here before it opens a model session. portal/accounts/ticket.py signs the same
way (neither imports the other, ADR 0002): tests/portal/test_test_call.py mints with that and checks with this,
and fails naming the side to edit.
"""

import hashlib
import hmac
import time
from urllib.parse import parse_qs

# The label keeps a ticket's signature from being reused as anything else the secret signs.
LABEL = b"call-ticket:"


def sign(secret: str, business_id: int, expires: int) -> str:
    """`<business id>.<expiry, unix seconds>.<signature>`: digits, hex and dots only, so it is safe in an address."""
    body = f"{business_id}.{expires}"
    mac = hmac.new(secret.encode(), LABEL + body.encode(), hashlib.sha256)
    return f"{body}.{mac.hexdigest()}"


def ticket_business(
    ticket: str | None, secret: str, now: float | None = None
) -> int | None:
    """The Business id a valid, unexpired ticket is for, else None. No secret set means no ticket is ever valid."""
    if not ticket or not secret:
        return None
    business, _, rest = ticket.partition(".")
    expires, _, signature = rest.partition(".")
    for part in (business, expires):
        # Short ASCII digits written the one way sign() writes them; int() raises on thousands of digits, so length first.
        if not (part.isascii() and part.isdigit() and len(part) <= 18):
            return None
        if part != str(int(part)):
            return None
    wanted = sign(secret, int(business), int(expires)).rpartition(".")[2]
    if not hmac.compare_digest(signature.encode(), wanted.encode()):
        return None
    if int(expires) < (time.time() if now is None else now):
        return None
    return int(business)


def from_query(query: bytes) -> str | None:
    """The ticket in a request's query string (`?ticket=...`), if any: the first one, and a blank one counts, so it is refused."""
    values = parse_qs(query.decode("latin-1"), keep_blank_values=True).get("ticket")
    return values[0] if values else None
