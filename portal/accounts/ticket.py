# pyright: basic
"""Signs the call ticket the core checks (voice/ticket.py): who the browser may call for, what started the call (a Call record's kind), the website allowed to frame the page (a call link's or demo call's, empty for a test call), and until when.

The format lives in voice/ticket.py and here, because neither service imports the other (ADR 0002);
tests/portal/test_test_call.py checks the two agree.
"""

import hashlib
import hmac
import time

LABEL = b"call-ticket:"
# From pressing the button here to pressing "start" on the core's page; the call itself may run longer.
TTL_SECONDS = 600


def sign(
    secret: str, business_id: int, kind: str, expires: int, domain: str = ""
) -> str:
    body = f"{business_id}.{kind}.{expires}.{domain}"
    mac = hmac.new(secret.encode(), LABEL + body.encode(), hashlib.sha256)
    return f"{body}.{mac.hexdigest()}"


def mint(secret: str, business_id: int, kind: str, domain: str = "") -> str:
    return sign(secret, business_id, kind, int(time.time()) + TTL_SECONDS, domain)
