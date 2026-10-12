"""Seam 2: the cap rule, free. The evals-approved fence on the caps file comes with PET-45."""

from evals.spend import Caps, stopped_by

CAPS = Caps(per_run_sek=10, per_loop_sek=30, per_day_sek=50)


def test_under_every_cap_runs_on() -> None:
    assert stopped_by(CAPS, run=1, loop=1, day=1) is None


def test_each_cap_stops_the_run() -> None:
    assert stopped_by(CAPS, run=10, loop=0, day=0) == "run cap 10 SEK"
    assert stopped_by(CAPS, run=0, loop=30, day=0) == "loop cap 30 SEK"
    assert stopped_by(CAPS, run=0, loop=0, day=50) == "day cap 50 SEK"


def test_committed_caps_are_the_approved_ones() -> None:
    # Parity: Petter's approved 10/30/50 SEK live here and in evals/caps.json; edit caps.json only with his OK.
    assert Caps.load() == CAPS
