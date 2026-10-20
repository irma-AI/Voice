"""Seam 2: the cost sum, free. The prices are a stored synthetic file, so a change to prices.json changes no test."""

from pathlib import Path

from tests.evals.cost import cost_sek

PRICES = Path(__file__).parent / "cost/synthetic_prices.json"


def test_no_usage_costs_nothing() -> None:
    assert cost_sek([], PRICES) == 0


def test_one_million_audio_out_tokens_at_the_listed_price() -> None:
    usage = [
        {
            "prompt_tokens": 0,
            "completion_tokens": 1_000_000,
            "output_audio_tokens": 1_000_000,
        }
    ]
    assert cost_sek(usage, PRICES) == 80.0  # $8 a million, 10 kr a dollar


def test_text_is_what_is_left_after_audio() -> None:
    usage = [
        {
            "prompt_tokens": 1_000_000,
            "input_audio_tokens": 400_000,
            "completion_tokens": 0,
        }
    ]
    # 400k audio at $2 and 600k text at $1 a million, 10 kr a dollar
    assert round(cost_sek(usage, PRICES), 6) == 14.0
