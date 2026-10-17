---
paths:
  - "**/*.py"
  - ".env.example"
---

# Security and personal data

- API keys and carrier credentials come from the environment only; never logged, never in fixtures.
- Call audio, transcripts, phone numbers and names never appear in logs or error messages; log call IDs instead.
- A skipped Module is logged by its name and the kind of failure only (`voice/modules.py`): a Module's address could hold a password, so it never reaches a log or error message the core writes. Pipecat's own log of a failed tool call is not covered (not checked).
- The barge-in log (`voice/bargein.py`) is timings and levels only. A production line may hold: `t`, `call`, `e`, and per event `vad`; `phase`, `played_ms`; `bot_speaking`, `bot_ms`, `peak_dbfs`, `rms_dbfs`, `src`; `words`, `after_barge_in_ms`; `reason`, `secs`. A new field is added here first.
- The Call record log (`voice/report.py`) is numbers, codes and times only, one `call record` line and one `usage` line per usage report, with an id for the call. A production line may hold: the record's `call_id`, `business`, `kind`, `started_at`, `length_seconds`, `prompt_tokens`, `completion_tokens`, `input_audio_tokens`, `output_audio_tokens`, `thinking_tokens`, `cached_tokens`, `cost_usd`, `price_date`, `cost_reason`; and per usage report `call`, `total_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`, `reasoning_tokens`, `cache_read_input_audio_tokens` besides the record's token counts. The price lookup (`voice/cost.py`) adds a `price match` line naming Google's catalogue entries that priced the call (or, when none matched, up to 20 entries naming the live model), and `price catalogue` lines with the status code or the kind of failure; entry names are Google's, never the key or the address. A failed send is logged by the Portal's host and the kind of failure only, never the address or the secret. A new field is added here first.
- The Portal stores a Module's name and address only, never a credential (the database refuses an address with a user, password, query or fragment); the address and the Module's answers stay out of its logs.
- The Portal holds a Business's email and name: personal data. They stay out of logs and error messages (the audit log names an account id), and an invite or reset link is a credential: it only ever goes by email, and prints to the console only on a local run (`DEBUG=1`).
- A Business's call link (`Business.call_slug`) is a credential for starting calls on Petter's Google key, with no limit yet: the dashboard shows it only to that Business, and it never goes in a log the core writes.
- The call button snippet puts a Business's call link (and so its slug) in the HTML of that Business's own website: the link is public by design, so that is no new exposure.
- Test fixtures use synthetic people only: generated names, +46 numbers we own or reserved test numbers, and personnummer that pass the checksum and are marked synthetic.
- Any real recording sits outside the repo.

## Enforced by

- Credentials in the repo: the `no-committed-secrets` guard.
- The Portal refuses to start without its secrets (`DJANGO_SECRET_KEY`, `CORE_SECRET`, `CORE_URL`) and mail settings outside a local run (`portal/settings.py`, `required`; `tests/portal/test_settings.py`).
- Personal data in logs, errors and fixtures, and real recordings: none yet. The barge-in field list above: none yet (the recorder's code is the only other copy of it). The Call record field list: `tests/test_report.py` fails when a record or usage field is missing from it.
