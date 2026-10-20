"""What a call cost, in US dollars, from Google's Cloud Billing Catalog (VOI-42).

The catalogue is Google's public price list (the v2beta SKU list and v1beta price endpoints that take an API key, per
https://cloud.google.com/billing/docs/how-to/get-pricing-information-api), asked for in dollars with `BILLING_API_KEY`. The price of each token kind is kept in memory for a day. When the catalogue can't be read, or its entries can't be matched to the Live model's
token kinds, the tokens are priced from the stored copy of Google's official rates (`STORED_PRICES`, dated by its `as_of`, VOI-216), so the daily budget sees a real cost; only when that copy is for another model or can't be read is the cost empty, with a `CostReason` saying why.
"""

import contextlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Any

from loguru import logger

from voice.portal_client import NoRedirect

# The model the core's calls run on and the one the price lookup prices; voice/agent.py imports it, so there is one name.
MODEL = "models/gemini-3.8-live"
CATALOGUE_URL = "https://cloudbilling.googleapis.com"
# The Generative Language API's service in the catalogue. shortcut: not yet seen with the real key (VOI-42's live read); a wrong id reads as `price_not_matched`, with the entries naming the live model in the log if the service id was right.
GEMINI_SERVICE = "services/AEFD-7695-64FA"
CATALOGUE_TIMEOUT_S = 10
MAX_PAGES = 20
KEPT_FOR_S = 24 * 3600
# Google's official per-token rates for MODEL, copied from ai.google.dev/gemini-api/docs/pricing (docs/research/gemini-live-pricing.md); the evals' cost caps read the same file.
STORED_PRICES = Path(__file__).parent / "prices.json"


class CostReason(StrEnum):
    """Why the live lookup failed. It reaches a record only when the stored rates can't price the call either; the Portal stores the code as is; tests/test_cost_catalogue.py reaches every one."""

    NO_KEY = "no_billing_key"
    UNREACHABLE = "catalogue_unreachable"
    UNREADABLE = "catalogue_unreadable"
    NOT_MATCHED = "price_not_matched"
    SHAPE_UNKNOWN = "price_shape_unknown"


class Unpriced(Exception):
    def __init__(self, reason: CostReason) -> None:
        super().__init__(reason.value)
        self.reason = reason


Kind = tuple[str, str]  # (direction, modality)
KINDS: tuple[Kind, ...] = (
    ("input", "audio"),
    ("input", "text"),
    ("output", "audio"),
    ("output", "text"),
)
# One day's prices: (when they were read, the UTC date they were read, dollars per token of each kind).
_kept: tuple[float, str, dict[Kind, Decimal]] | None = None


def token_kinds(totals: Mapping[str, int]) -> dict[Kind, int]:
    """The record's counts as billed tokens per (direction, modality). Text is what is left after audio; thinking bills as
    text output; cached tokens stay in the prompt at the full rate (no cached price is listed, so this can only over-count)."""
    audio_in, audio_out = totals["input_audio_tokens"], totals["output_audio_tokens"]
    return {
        ("input", "audio"): audio_in,
        ("input", "text"): max(totals["prompt_tokens"] - audio_in, 0),
        ("output", "audio"): audio_out,
        ("output", "text"): max(totals["completion_tokens"] - audio_out, 0)
        + totals["thinking_tokens"],
    }


def _get(url: str) -> dict[str, Any]:
    """One catalogue request. Logs only Google's own status words (never the address, which holds the key)."""
    try:
        with urllib.request.build_opener(NoRedirect).open(
            url, timeout=CATALOGUE_TIMEOUT_S
        ) as reply:
            return json.loads(reply.read())
    except urllib.error.HTTPError as e:
        words = ""
        with contextlib.suppress(
            Exception
        ):  # an answer that is not Google's error shape: the code alone
            error = json.loads(e.read(10_000))["error"]
            reasons = [d.get("reason", "") for d in error.get("details", [])]
            words = " ".join(
                w
                for w in [error["status"], *reasons]
                if re.fullmatch(r"[A-Z_]{1,60}", w)
            )
        logger.warning("price catalogue answered {} {}", e.code, words)
        raise Unpriced(CostReason.UNREADABLE) from None
    except json.JSONDecodeError:
        raise Unpriced(CostReason.UNREADABLE) from None
    except Exception as e:  # noqa: BLE001  the kind only: a message could hold the key
        logger.warning("price catalogue not reached ({})", type(e).__name__)
        raise Unpriced(CostReason.UNREACHABLE) from None


def _skus(key: str, base: str) -> list[dict[str, Any]]:
    """Every entry of the Generative Language API: (skuId, displayName)."""
    skus: list[dict[str, Any]] = []
    token = ""
    for _ in range(MAX_PAGES):
        query = {
            "filter": f'service="{GEMINI_SERVICE}"',
            "pageSize": "5000",
            "key": key,
        }
        if token:
            query["pageToken"] = token
        page = _get(f"{base}/v2beta/skus?{urllib.parse.urlencode(query)}")
        skus += page.get("skus", [])
        token = page.get("nextPageToken", "")
        if not token:
            return skus
    raise Unpriced(CostReason.UNREADABLE)


def _words(text: str) -> str:
    return text.lower().replace("-", " ").replace("_", " ")


def _match(skus: list[dict[str, Any]], model: str, kind: Kind) -> dict[str, Any]:
    """The one entry naming the model, the direction and the modality. None or several: the price would be a guess."""
    name, (direction, modality) = _words(model.removeprefix("models/")), kind

    def is_it(sku: dict[str, Any]) -> bool:
        d = _words(sku.get("displayName", ""))
        # The name ends the entry: "gemini 3.8 live" must not also take "gemini 3.8 live extended thinking".
        if not d.endswith(name) or direction not in d:
            return False
        if modality == "audio":
            return "audio" in d
        return not any(other in d for other in ("audio", "image", "video"))

    found = [s for s in skus if is_it(s)]
    if len(found) != 1:
        # Google's own entry names (no caller data), so the first real call shows what to match.
        live = [
            s.get("displayName")
            for s in skus
            if "live" in _words(s.get("displayName", ""))
        ]
        logger.warning(
            "price match: {} entries for {} {}; entries naming live: {}",
            len(found),
            *kind,
            live[:20],
        )
        raise Unpriced(CostReason.NOT_MATCHED)
    return found[0]


def _per_token(price: dict[str, Any]) -> Decimal:
    """Dollars per token from a v1beta price: one flat tier from zero, in dollars, per `unitQuantity` counted units."""
    try:
        rate = price["rate"]
        (tier,) = rate["tiers"]
        listed = tier["listPrice"]
        if (
            price["currencyCode"] != "USD"
            or listed["currencyCode"] != "USD"
            or Decimal(tier["startAmount"]["value"]) != 0
        ):
            raise ValueError
        dollars = (
            Decimal(int(listed.get("units", 0)))
            + Decimal(int(listed.get("nanos", 0))) / 10**9
        )
        per = dollars / Decimal(rate["unitInfo"]["unitQuantity"]["value"])
        # No real token costs a dollar or more, nothing or less; such a rate would misprice a day of calls or overflow the sum.
        if not (per.is_finite() and 0 < per < 1):
            raise ValueError
        return per
    except (KeyError, ValueError, TypeError, ArithmeticError):
        raise Unpriced(CostReason.SHAPE_UNKNOWN) from None


def rates(
    key: str, model: str, base: str = CATALOGUE_URL
) -> tuple[str, dict[Kind, Decimal]]:
    """(the UTC date read, dollars per token of each kind), from memory when read within the day. Blocks, so it runs in a thread."""
    global _kept
    if _kept and time.monotonic() - _kept[0] < KEPT_FOR_S:
        return _kept[1], _kept[2]
    skus = _skus(key, base)
    per_token: dict[Kind, Decimal] = {}
    matched: list[str | None] = []
    for kind in KINDS:
        sku = _match(skus, model, kind)
        query = urllib.parse.urlencode({"currencyCode": "USD", "key": key})
        per_token[kind] = _per_token(
            _get(f"{base}/v1beta/skus/{sku['skuId']}/price?{query}")
        )
        matched.append(sku.get("displayName"))
    logger.info("price match: {}", matched)
    date = datetime.now(UTC).date().isoformat()
    _kept = (time.monotonic(), date, per_token)
    return date, per_token


def stored_rates(model: str, stored: Path) -> tuple[str, dict[Kind, Decimal]] | None:
    """(the copy's as_of date, dollars per token of each kind) from the stored official rates, or None when they are not for this model."""
    try:
        copy = json.loads(stored.read_text("utf-8"))
        if copy["model"] != model:
            return None
        per_m = copy["usd_per_million_tokens"]
        names = {
            ("input", "audio"): "audio_in",
            ("input", "text"): "text_in",
            ("output", "audio"): "audio_out",
            ("output", "text"): "text_out",
        }
        per_token = {kind: Decimal(str(per_m[names[kind]])) / 10**6 for kind in KINDS}
        # A bad edit must leave the call unpriced (the Portal counts its seconds), never lose its record.
        if not all(r.is_finite() and r > 0 for r in per_token.values()):
            return None
        return datetime.fromisoformat(copy["as_of"]).date().isoformat(), per_token
    except (OSError, ValueError, KeyError, TypeError, ArithmeticError):
        return None


def price(
    totals: Mapping[str, int],
    model: str,
    key: str,
    base: str = CATALOGUE_URL,
    stored: Path | None = STORED_PRICES,
) -> dict[str, str | None]:
    """The record's three cost fields (cost_usd, price_date, cost_reason) for one call's tokens. Blocks, so it runs in a thread."""
    try:
        if not key:
            raise Unpriced(CostReason.NO_KEY)
        date, per_token = rates(key, model, base)
    except Exception as e:  # noqa: BLE001  a reply our parsing trips on must not lose the Call record
        if isinstance(e, Unpriced):
            reason = e.reason
        else:
            reason = CostReason.UNREADABLE
            logger.warning("price catalogue unreadable ({})", type(e).__name__)
        fallback = stored_rates(model, stored) if stored else None
        if not fallback:
            return {"cost_usd": None, "price_date": None, "cost_reason": reason.value}
        date, per_token = fallback
        logger.warning(
            "price catalogue failed ({}): priced from the stored rates of {}",
            reason.value,
            date,
        )
    total = sum(
        (per_token[kind] * tokens for kind, tokens in token_kinds(totals).items()),
        Decimal(0),
    )
    cost = format(total.quantize(Decimal("0.00000001")), "f")
    return {"cost_usd": cost, "price_date": date, "cost_reason": None}
