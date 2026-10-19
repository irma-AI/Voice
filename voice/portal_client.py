"""The Portal client: the one way the core reaches the Portal (VOI-168).

It alone reads the Portal's address (`SETTINGS_URL`) and the shared secret (`CORE_SECRET`), and holds the rules every
Portal request keeps: the secret goes as a Bearer token, a redirect is never followed (it would carry the secret
along), and a log line or error names the Portal's host and the kind of failure only (the address could hold a
password, an error message the secret). `get` tries once and fails closed (the settings fetch); `post` tries again
for up to a minute (the Call record and Call log sends). The Portal never imports this, and this never imports it.
"""

import json
import os
import time
import urllib.error
import urllib.request
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit

from loguru import logger

# ponytail: a call waits this long in silence for the Portal before it is refused; make it a setting if the Portal is slow in practice.
TIMEOUT_S = 5
# ponytail: a fixed pause between tries; back off if the Portal is ever seen struggling under them.
RETRY_WINDOW_S = 60
RETRY_PAUSE_S = 5


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect would carry the secret to wherever it points; a moved Portal is a refused request."""

    def redirect_request(self, *_: Any, **__: Any) -> None:
        return None


class PortalRefused(Exception):
    """No answer from the Portal. The message goes in the log, so it names the host and the kind of failure only."""


def core_secret(env: Mapping[str, str] = os.environ) -> str:
    """The secret the Portal and the core share: it signs call tickets (voice/ticket.py) and opens the Portal's API."""
    return env.get("CORE_SECRET", "")


def _portal(env: Mapping[str, str]) -> tuple[str, str]:
    return env.get("SETTINGS_URL", "").strip(), core_secret(env)


def _open(url: str, key: str, path: str, body: bytes | None = None) -> Any:
    headers = {"Authorization": f"Bearer {key}"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(f"{url.rstrip('/')}{path}", body, headers)
    return urllib.request.build_opener(NoRedirect).open(request, timeout=TIMEOUT_S)


def get(
    path: str, what: str, limit: int, env: Mapping[str, str] = os.environ
) -> object:
    """The Portal's JSON answer at `path`, read up to `limit` bytes. One try: any failure raises `PortalRefused`."""
    url, key = _portal(env)
    if not key:
        raise PortalRefused("SETTINGS_URL is set but CORE_SECRET is missing")
    parts = urlsplit(url)
    host = parts.hostname
    if parts.scheme not in ("http", "https") or not host:
        raise PortalRefused("SETTINGS_URL must be an http or https address")
    try:
        with _open(url, key, path) as reply:
            return json.loads(reply.read(limit))
    except urllib.error.HTTPError as e:
        raise PortalRefused(f"the Portal at {host} answered {e.code}") from None
    except Exception as e:  # noqa: BLE001  fail closed: unreachable, cut short, not JSON, too deep: all refuse, and only the kind is logged (a message could hold the secret)
        raise PortalRefused(
            f"the Portal at {host} gave no {what} ({type(e).__name__})"
        ) from None


def post(
    path: str,
    body: Mapping[str, Any],
    what: str,
    env: Mapping[str, str] = os.environ,
    window_s: float = RETRY_WINDOW_S,
    pause_s: float = RETRY_PAUSE_S,
) -> bool:
    """Posts one call's `body` (it holds `call_id`) to `path`, trying again for up to `window_s` seconds. Blocks, so it runs in a thread."""
    call = body["call_id"]
    url, key = _portal(env)
    if not (url and key):
        logger.error(
            "call {}: {} not sent, SETTINGS_URL or CORE_SECRET is not set", call, what
        )
        return False
    host = urlsplit(url).hostname
    data = json.dumps(body).encode()
    deadline = time.monotonic() + window_s
    while True:
        try:
            with _open(url, key, path, data):
                logger.info("call {}: {} delivered to the Portal", call, what)
                return True
        except urllib.error.HTTPError as e:
            why = f"answered {e.code}"
        except Exception as e:  # noqa: BLE001  the kind only: a message could hold the secret
            why = type(e).__name__
        if time.monotonic() + pause_s > deadline:
            logger.error(
                "call {}: gave up sending the {} to the Portal at {} ({}); the log lines above are the only copy",
                call,
                what,
                host,
                why,
            )
            return False
        logger.warning(
            "call {}: {} not delivered to the Portal at {} ({}), trying again",
            call,
            what,
            host,
            why,
        )
        time.sleep(pause_s)
