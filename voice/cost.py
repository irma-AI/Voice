"""What a call cost, in US dollars, from Google's Cloud Billing Catalog (VOI-42).

The catalogue is Google's public price list, asked for in dollars with the core's own Google key and kept in memory for a
day. No price is written down here. When the catalogue can't be read, or its entries can't be matched to the Live model's
token kinds, the cost is empty and a `CostReason` says why: a wrong price is worse than none.
"""

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from loguru import logger

from voice.settings import NoRedirect

# The model the core's calls run on and the one the price lookup prices; voice/agent.py imports it, so there is one name.
MODEL = "models/gemini-3.8-live"
CATALOGUE_URL = "https://cloudbilling.googleapis.com/v1"
# The Generative Language API's service in the catalogue. ponytail: not yet seen with the real key (VOI-42's live read); a wrong id reads as `catalogue_unreadable`.
GEMINI_SERVICE = "AEFD-7695-64FA"
CATALOGUE_TIMEOUT_S = 10
MAX_PAGES = 20
KEPT_FOR_S = 24 * 3600


class CostReason(StrEnum):
    """Why a record has no cost. The Portal stores the code as is; tests/test_cost_catalogue.py reaches every one."""

    NO_KEY = "no_google_key"
    UNREACHABLE = "catalogue_unreachable"
    UNREADABLE = "catalogue_unreadable"
    NOT_MATCHED = "price_not_matched"
    SHAPE_UNKNOWN = "price_shape_unknown"


class Unpriced(Exception):
    def __init__(self, reason: CostReason) -> None:
        super().__init__(reason.value)
        self.reason = reason


# One day's catalogue: (when it was kept, the entries).
_kept: tuple[float, list[dict[str, Any]]] | None = None


def token_kinds(totals: Mapping[str, int]) -> dict[tuple[str, str], int]:
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


def _fetch(key: str, base: str) -> list[dict[str, Any]]:
    skus: list[dict[str, Any]] = []
    token = ""
    for _ in range(MAX_PAGES):
        query = {"currencyCode": "USD", "pageSize": "5000", "key": key}
        if token:
            query["pageToken"] = token
        url = f"{base}/services/{GEMINI_SERVICE}/skus?{urllib.parse.urlencode(query)}"
        try:
            with urllib.request.build_opener(NoRedirect).open(
                url, timeout=CATALOGUE_TIMEOUT_S
            ) as reply:
                page = json.loads(reply.read())
        except urllib.error.HTTPError as e:
            logger.warning("price catalogue answered {}", e.code)
            raise Unpriced(CostReason.UNREADABLE) from None
        except json.JSONDecodeError:
            raise Unpriced(CostReason.UNREADABLE) from None
        except Exception as e:  # noqa: BLE001  the kind only: a message could hold the key
            logger.warning("price catalogue not reached ({})", type(e).__name__)
            raise Unpriced(CostReason.UNREACHABLE) from None
        skus += page.get("skus", [])
        token = page.get("nextPageToken", "")
        if not token:
            return skus
    raise Unpriced(CostReason.UNREADABLE)


def catalogue(key: str, base: str = CATALOGUE_URL) -> list[dict[str, Any]]:
    """The Generative Language API's entries in dollars, from memory when read within the day. Blocks, so it runs in a thread."""
    global _kept
    if _kept and time.monotonic() - _kept[0] < KEPT_FOR_S:
        return _kept[1]
    skus = _fetch(key, base)
    _kept = (time.monotonic(), skus)
    return skus


def _words(text: str) -> str:
    return text.lower().replace("-", " ").replace("_", " ")


def _match(
    skus: list[dict[str, Any]], model: str, direction: str, modality: str
) -> dict[str, Any]:
    """The one on-demand entry naming the model, the direction and the modality. None or several: the price would be a guess."""
    name = _words(model.removeprefix("models/"))

    def is_it(sku: dict[str, Any]) -> bool:
        d = _words(sku.get("description", ""))
        if name not in d or direction not in d:
            return False
        if sku.get("category", {}).get("usageType", "OnDemand") != "OnDemand":
            return False
        if modality == "audio":
            return "audio" in d
        return not any(other in d for other in ("audio", "image", "video"))

    found = [s for s in skus if is_it(s)]
    if len(found) != 1:
        raise Unpriced(CostReason.NOT_MATCHED)
    return found[0]


def _per_token(sku: dict[str, Any]) -> tuple[Decimal, str]:
    """(dollars per token, the date that price took effect) of an entry with one flat rate per counted unit."""
    try:
        info = max(sku["pricingInfo"], key=lambda p: p["effectiveTime"])
        expression = info["pricingExpression"]
        (tier,) = expression["tieredRates"]
        price = tier["unitPrice"]
        if (
            price["currencyCode"] != "USD"
            or expression["baseUnit"] != "count"
            or int(tier.get("startUsageAmount", 0)) != 0
        ):
            raise ValueError
        dollars = (
            Decimal(int(price.get("units", 0)))
            + Decimal(int(price.get("nanos", 0))) / 10**9
        )
        per_token = dollars / Decimal(expression["baseUnitConversionFactor"])
        date = datetime.fromisoformat(info["effectiveTime"]).date().isoformat()
    except (KeyError, ValueError, TypeError, ArithmeticError):
        raise Unpriced(CostReason.SHAPE_UNKNOWN) from None
    return per_token, date


def price(
    totals: Mapping[str, int], model: str, key: str, base: str = CATALOGUE_URL
) -> dict[str, str | None]:
    """The record's three cost fields (cost_usd, price_date, cost_reason) for one call's tokens. Blocks, so it runs in a thread."""
    try:
        if not key:
            raise Unpriced(CostReason.NO_KEY)
        skus = catalogue(key, base)
        total, dates, matched = Decimal(0), list[str](), list[str | None]()
        for kind, tokens in token_kinds(totals).items():
            try:
                sku = _match(skus, model, *kind)
            except Unpriced:
                # Google's own entry names (no caller data), so the first real call shows what to match.
                live = [
                    s.get("description")
                    for s in skus
                    if "live" in _words(s.get("description", ""))
                ]
                logger.warning(
                    "price match: none for {} {}; entries naming live: {}",
                    *kind,
                    live[:20],
                )
                raise
            per_token, date = _per_token(sku)
            total += per_token * tokens
            dates.append(date)
            matched.append(sku.get("description"))
        logger.info("price match: {}", matched)
        cost = format(total.quantize(Decimal("0.00000001")), "f")
        return {"cost_usd": cost, "price_date": max(dates), "cost_reason": None}
    except Unpriced as e:
        return {"cost_usd": None, "price_date": None, "cost_reason": e.reason.value}
