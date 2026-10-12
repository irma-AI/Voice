"""What a call cost, from the usage the model reported. Prices are data in prices.json."""

import json
from pathlib import Path
from typing import Any

PRICES_FILE = Path(__file__).parent / "prices.json"


def cost_sek(
    usage_events: list[dict[str, Any]], prices_file: Path = PRICES_FILE
) -> float:
    """Sums every usage report (each counted as a delta; if the model reports running totals this over-counts, which is the safe side for a cap)."""
    prices = json.loads(prices_file.read_text("utf-8"))
    per_m = prices["usd_per_million_tokens"]
    usd = 0.0
    for u in usage_events:
        audio_in = u.get("input_audio_tokens", 0)
        audio_out = u.get("output_audio_tokens", 0)
        text_in = max(u.get("prompt_tokens", 0) - audio_in, 0)
        # Thinking tokens are billed as output; counted on top in case the model reports them apart.
        text_out = max(u.get("completion_tokens", 0) - audio_out, 0) + u.get(
            "reasoning_tokens", 0
        )
        usd += (
            audio_in * per_m["audio_in"]
            + text_in * per_m["text_in"]
            + audio_out * per_m["audio_out"]
            + text_out * per_m["text_out"]
        ) / 1e6
    return usd * prices["sek_per_usd"]
