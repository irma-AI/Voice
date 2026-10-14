# pyright: basic
"""Signs the call ticket the core checks (voice/ticket.py): who the browser may call for, and until when.

The format lives in voice/ticket.py and here, because neither service imports the other (ADR 0002);
tests/portal/test_test_call.py checks the two agree.
"""

import hashlib
import hmac
import time

LABEL = b"call-ticket:"
# From pressing the button here to pressing "start" on the core's page; the call itself may run longer.
TTL_SECONDS = 600


def sign(secret: str, business_id: int, expires: int) -> str:
    body = f"{business_id}.{expires}"
    mac = hmac.new(secret.encode(), LABEL + body.encode(), hashlib.sha256)
    return f"{body}.{mac.hexdigest()}"


def mint(secret: str, business_id: int) -> str:
    return sign(secret, business_id, int(time.time()) + TTL_SECONDS)
