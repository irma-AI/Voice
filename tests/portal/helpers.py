"""Helpers the Portal tests share."""

# pyright: basic
# (django-stubs types model fields for mypy's plugin; strict pyright cannot read them)

from datetime import datetime
from typing import Any

from django.test import Client

from portal import synthetic
from portal.accounts.models import Account, Business, CallRecord

PASSWORD = "a-long-passphrase-for-tests"
SECRET = "a-secret-for-tests"


def business_with_login(
    email: str | None = None, name: str | None = None
) -> tuple[Business, Client]:
    """A Business with its Account, and a test client logged in as it; synthetic (portal/synthetic.py) unless the test names them."""
    email = email or synthetic.email()
    account = Account.objects.create_user(email, PASSWORD)
    business = Business.objects.create(
        account=account, name=name or synthetic.business_name()
    )
    client = Client()
    assert client.login(email=email, password=PASSWORD)
    return business, client


def ask_core(business_id: int, secret: str | None = SECRET) -> Any:
    """The core's request for a Business's settings, as its settings port sends it."""
    headers = {} if secret is None else {"Authorization": f"Bearer {secret}"}
    return Client().get(f"/api/settings/{business_id}/", headers=headers)


def told_to_core(business: Business, settings: Any) -> dict[str, Any]:
    """What the settings address tells the core about this Business."""
    settings.CORE_SECRET = SECRET
    return ask_core(business.pk).json()


def a_call(owner: Business, call_id: str, started: datetime, **changes: Any) -> None:
    CallRecord.objects.create(
        **{
            "call_id": call_id,
            "business": owner,
            "kind": "call_link",
            "started_at": started,
            "length_seconds": 184,
            "prompt_tokens": 1,
            "completion_tokens": 1,
            "input_audio_tokens": 1,
            "output_audio_tokens": 1,
            "thinking_tokens": 0,
            "cached_tokens": 0,
            "cost_usd": "0.01234567",
            "price_date": "2026-10-17",
            **changes,
        }
    )


CALL = "c0ffee-0123456789"
# The core's own lines (voice/bargein.py), one of each event.
EVENTS: list[dict[str, Any]] = [
    {
        "t": 0.0,
        "call": CALL,
        "e": "config",
        "vad": {"start_sensitivity": "START_SENSITIVITY_LOW", "prefix_padding_ms": 300},
        "page_facts": "sent",
        "echo_cancellation": True,
        "noise_suppression": "remote-only",
        "auto_gain_control": False,
        "loopback": "set_up",
        "sample_rate": 48000,
        "base_latency_ms": 5.3,
        "output_latency_ms": 21.0,
        "browser": "safari",
        "os": "ios",
        "os_version": 18,
    },
    {"t": 1.2, "call": CALL, "e": "bot_speech", "phase": "start"},
    {
        "t": 2.5,
        "call": CALL,
        "e": "barge_in",
        "bot_speaking": True,
        "bot_ms": 1300,
        "peak_dbfs": -12.5,
        "rms_dbfs": -30.1,
        "src": "gemini",
        "echo_corr": 0.12,
        "echo_lag_ms": 180,
    },
    {"t": 2.6, "call": CALL, "e": "bot_speech", "phase": "stop", "played_ms": 1400},
    {
        "t": 3.0,
        "call": CALL,
        "e": "levels",
        "after_barge_in_ms": 500,
        "caller_dbfs": [
            -60.2,
            -58.0,
            -31.5,
            -25.0,
            -24.1,
            -26.3,
            -28.0,
            -30.2,
            -45.0,
            -60.0,
        ],
        "bot_dbfs": [
            -20.1,
            -19.5,
            -21.0,
            -20.4,
            -22.0,
            -100.0,
            -100.0,
            -100.0,
            -100.0,
            -100.0,
        ],
    },
    {
        "t": 3.1,
        "call": CALL,
        "e": "caller_words",
        "words": 4,
        "after_barge_in_ms": 600,
        "similarity": 0.0,
    },
    {"t": 4.0, "call": CALL, "e": "resumed", "after_barge_in_ms": 1500},
    {
        "t": 9.9,
        "call": CALL,
        "e": "end",
        "reason": "cancel",
        "secs": 9.9,
        "barge_ins": 1,
        "no_words": 0,
        "cut_share": 1.0,
        "playback_gaps": 2,
    },
]


def a_log(owner: Business, **changes: Any) -> dict[str, Any]:
    return {
        "call_id": CALL,
        "business": owner.pk,
        "kind": "test",
        "started_at": "2026-10-19T05:00:00.000000Z",
        "events": EVENTS,
        **changes,
    }
