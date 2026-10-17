"""What a call cost, from the usage the model reported. Prices are data in prices.json."""

import json
from pathlib import Path
from typing import Any

from voice.cost import token_kinds

PRICES_FILE = Path(__file__).parent / "prices.json"


def cost_sek(
    usage_events: list[dict[str, Any]], prices_file: Path = PRICES_FILE
) -> float:
    """Sums every usage report (each counted as a delta; if the model reports running totals this over-counts, which is the safe side for a cap)."""
    prices = json.loads(prices_file.read_text("utf-8"))
    per_m = prices["usd_per_million_tokens"]
    usd = 0.0
    for u in usage_events:
        # The core's own token split (voice/cost.py); thinking tokens go in under the name the record uses.
        kinds = token_kinds(
            {
                "prompt_tokens": u.get("prompt_tokens", 0),
                "completion_tokens": u.get("completion_tokens", 0),
                "input_audio_tokens": u.get("input_audio_tokens", 0),
                "output_audio_tokens": u.get("output_audio_tokens", 0),
                "thinking_tokens": u.get("reasoning_tokens", 0),
            }
        )
        usd += (
            kinds["input", "audio"] * per_m["audio_in"]
            + kinds["input", "text"] * per_m["text_in"]
            + kinds["output", "audio"] * per_m["audio_out"]
            + kinds["output", "text"] * per_m["text_out"]
        ) / 1e6
    return usd * prices["sek_per_usd"]
