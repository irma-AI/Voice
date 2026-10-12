"""Seam 2: the cost sum, free."""

from tests.evals.cost import cost_sek


def test_no_usage_costs_nothing() -> None:
    assert cost_sek([]) == 0


def test_one_million_audio_out_tokens_at_the_listed_price() -> None:
    usage = [
        {
            "prompt_tokens": 0,
            "completion_tokens": 1_000_000,
            "output_audio_tokens": 1_000_000,
        }
    ]
    assert cost_sek(usage) == 12.0 * 11.0


def test_text_is_what_is_left_after_audio() -> None:
    usage = [
        {
            "prompt_tokens": 1_000_000,
            "input_audio_tokens": 400_000,
            "completion_tokens": 0,
        }
    ]
    assert round(cost_sek(usage), 6) == round((0.4 * 3.0 + 0.6 * 0.75) * 11.0, 6)
