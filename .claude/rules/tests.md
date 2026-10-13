---
paths:
  - "tests/**"
  - "**/test_*.py"
---

# Tests

Checks are `tests/test_<module>.py`; the ones that judge a call read the stored synthetic call records in `tests/calls/`. Scenarios, their Caller audio and the runner are `tests/evals/`. Each kind below catches what the others can't.

- **Sweep tests** read the whole set from the source and fail for any member that breaks a rule, so a new member is checked even if its author never opens the test. Here: every Scenario is in the runner, the manifest, the Scenario files and the audio list (`tests/test_eval_run.py`).
- **Parity tests** cover a fact that lives in two places that can't share code. The test reads both sides, and its failure names the side to edit. None yet.
- **Flaky tests** get one rerun to confirm. A test that fails and then passes gets a ticket and a fix in this PR or the next; it is never skipped, quarantined or deleted to get green.

## Enforced by

- `scripts/checks/guards/eval-required.js`: a change to what only the evals can test needs a receipt from a passing full `make eval` (`scripts/eval-required.json` lists it, `scripts/eval-receipt.js` hashes it). A hand-written receipt would pass; review checks the receipt came from `make eval`.
