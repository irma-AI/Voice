"""The calls port: the Portal lets each call start and is told how long it ran.

The Portal counts calls and minutes against a Business's limits and says yes or no (portal/accounts/models.py
`start_call`); the core opens no model session without its yes (ADR 0002, VOI-29). Settings from a file have no
Portal behind them, so they have no limits. Anything the Portal cannot answer refuses the call, like the settings
port; telling it how long a call ran never blocks anything, and a report that is lost counts as the longest a call can be.
"""

import json
import os
import time
import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from loguru import logger

from voice.settings import (
    MAX_REPLY_BYTES,
    PORTAL_TIMEOUT_S,
    NoRedirect,
    Settings,
    SettingsRefused,
)

# Why the Portal says no, and what the Caller is shown instead of a call (no model session opens, so nothing is spoken).
# portal/accounts/models.py OFF and LIMIT are the same two words; tests/portal/test_calls.py fails when they differ.
# Wording for callers: Petter's call (CLAUDE.md § Stop and ask).
REFUSED = {
    "off": "Tyvärr tar den här tjänsten inte emot samtal just nu.",
    "limit": "Tyvärr har vi nått dagens gräns för samtal, försök igen i morgon.",
}


class NotLetStart(Exception):
    """The Portal said no, for a reason in REFUSED. No model session was opened; the Channel shows `text` to the Caller."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"the Portal did not let the call start: {reason}")
        self.text = REFUSED[reason]


@dataclass(frozen=True)
class Call:
    """A call the Portal let start: its number there, and when it began."""

    id: int
    began: float  # time.monotonic()


def _post(address: str, secret: str, body: dict[str, Any]) -> tuple[int, object]:
    """The status and JSON of the Portal's answer; an error status is an answer, not an exception."""
    request = urllib.request.Request(
        address,
        data=json.dumps(body).encode(),
        method="POST",
        headers={
            "Authorization": f"Bearer {secret}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.build_opener(NoRedirect).open(
            request, timeout=PORTAL_TIMEOUT_S
        ) as reply:
            status, raw = reply.status, reply.read(MAX_REPLY_BYTES)
    except urllib.error.HTTPError as e:
        status, raw = e.code, e.read(MAX_REPLY_BYTES)
    try:
        return status, json.loads(raw)
    except ValueError:
        return status, None


def start(settings: Settings, env: Mapping[str, str] = os.environ) -> Call | None:
    """Asks the Portal to let a call start. None when the settings did not come from the Portal, so there is nothing to count against."""
    if settings.business_id is None:
        return None
    base, secret = env["SETTINGS_URL"].rstrip("/"), env["CORE_SECRET"]
    host = urlsplit(
        base
    ).hostname  # the log names the host only, never the address or the secret
    try:
        status, body = _post(
            f"{base}/api/businesses/{settings.business_id}/calls/", secret, {}
        )
    except Exception as e:  # noqa: BLE001  fail closed: unreachable, cut short: all refuse, and only the kind is logged
        raise SettingsRefused(
            f"the Portal at {host} would not start a call ({type(e).__name__})"
        ) from None
    answer: dict[str, Any] = body if isinstance(body, dict) else {}  # pyright: ignore[reportUnknownVariableType]
    if status == 201 and isinstance(answer.get("call"), int):
        return Call(answer["call"], time.monotonic())
    refused = answer.get("refused")
    if status == 403 and isinstance(refused, str) and refused in REFUSED:
        raise NotLetStart(refused)
    raise SettingsRefused(f"the Portal at {host} answered {status} to a call start")


def finish(call: Call, env: Mapping[str, str] = os.environ) -> None:
    """Tells the Portal how long the call ran. Never raises and never blocks a call: a lost report only makes the Portal count the call as the longest it can be."""
    seconds = round(time.monotonic() - call.began)
    try:
        status, _ = _post(
            f"{env['SETTINGS_URL'].rstrip('/')}/api/calls/{call.id}/end/",
            env["CORE_SECRET"],
            {"seconds": seconds},
        )
        if status != 200:
            logger.warning("the Portal answered {} to a call's end report", status)
    except Exception as e:  # noqa: BLE001  a report is best effort; only the kind is logged
        logger.warning("could not report a call's end ({})", type(e).__name__)
