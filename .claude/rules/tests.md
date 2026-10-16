---
paths:
  - "tests/**"
  - "**/test_*.py"
---

# Tests

Checks are `tests/test_<module>.py`; the ones that judge a call read the stored synthetic call records in `tests/calls/`. Scenarios, their Caller audio and the runner are `tests/evals/`. Each kind below catches what the others can't.

- **Sweep tests** read the whole set from the source and fail for any member that breaks a rule, so a new member is checked even if its author never opens the test. Here: every Scenario is in the runner, the manifest and the Scenario files, and every Caller audio file it plays is either rendered by `make eval-audio` or has a `<name>.licence.md` beside it (`tests/test_eval_run.py`), and every Portal page is behind the login or listed open (`tests/portal/test_routes.py`).
- **Parity tests** cover a fact that lives in two places that can't share code. The test reads both sides, and its failure names the side to edit. `tests/portal/test_settings_contract.py` (the settings schema against the Portal's model, form and languages) and `tests/test_settings_port.py` (the same schema against the core's limits and what it accepts), and `tests/portal/test_test_call.py` (the Portal signs the call ticket, the core checks it).
- **Real-store tests** (`tests/portal/`, marked `db`, run by `make test-db` against a Postgres it starts and stops) make the bad write or request and assert the refusal; a data rule that only a mock refuses is not tested. Add `@pytest.mark.db` (see the module-level `pytestmark` in `tests/portal/test_accounts.py`) to any test that needs the database.
- **Flaky tests** get one rerun to confirm. A test that fails and then passes gets a ticket and a fix in this PR or the next; it is never skipped, quarantined or deleted to get green.

## Enforced by

- `scripts/checks/guards/db-test-required.js`: a changed Portal migration needs a change under `tests/portal/`, or `db-test: skip <reason>` in the migration (`scripts/checks/db-test-required.json`).
- `scripts/checks/guards/eval-required.js`: a change to what only the evals can test needs a receipt from a passing full `make eval` (`scripts/eval-required.json` lists it, `scripts/eval-receipt.js` hashes it). A hand-written receipt would pass; review checks the receipt came from `make eval`.
