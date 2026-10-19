---
paths:
  - "**/*.py"
  - ".env.example"
---

# Security and personal data

- API keys and carrier credentials come from the environment only; never logged, never in fixtures.
- Call audio, transcripts, phone numbers and names never appear in logs or error messages; log call IDs instead.
- The Live transcript goes only to the Caller's own call page over the call socket (`voice/serve.py`): never logged, kept or put in the Call record.
- A skipped Module is logged by its name and the kind of failure only (`voice/modules.py`): a Module's address could hold a password, so it never reaches a log or error message the core writes. Pipecat's own log of a failed tool call is not covered (not checked).
- The barge-in log (`voice/bargein.py`) is timings and levels only. A production line may hold: `t`, `call`, `e`, and per event `vad`; `phase`, `played_ms`; `bot_speaking`, `bot_ms`, `peak_dbfs`, `rms_dbfs`, `src`; `words`, `after_barge_in_ms`; `reason`, `secs`. A new field is added here first.
- The Call log the Portal stores (`CallLog`, VOI-153) is a call's barge-in lines as the core logged them, beside the call's id, Business, kind and start time: an event holds the barge-in fields above and nothing else, each a number, true or false, or a short code with no space (`vad` an object of the same), and the database refuses anything else (migration 0020). A new field goes in the list above, the contract (`contract/call-log.schema.json`) and a new migration redefining `accounts_call_log_fields()`.
- The Call record log (`voice/report.py`) is numbers, codes and times only, one `call record` line and one `usage` line per usage report, with an id for the call. A production line may hold: the record's `call_id`, `business`, `kind`, `started_at`, `length_seconds`, `prompt_tokens`, `completion_tokens`, `input_audio_tokens`, `output_audio_tokens`, `thinking_tokens`, `cached_tokens`, `cost_usd`, `price_date`, `cost_reason`; and per usage report `call`, `total_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`, `reasoning_tokens`, `cache_read_input_audio_tokens` besides the record's token counts. The price lookup (`voice/cost.py`) adds a `price match` line naming Google's catalogue entries that priced the call (or, when none matched, up to 20 entries naming the live model), and `price catalogue` lines with the status code and Google's own error words (`status` and `reason`, capital letters and underscores only) or the kind of failure; entry names are Google's, never the key or the address. A new field is added here first.
- `voice/portal_client.py` is the only core module that reads the shared secret (`CORE_SECRET`) or builds a Portal request (`voice/settings.py` reads `SETTINGS_URL` only to choose its source and log the host): a failed request is logged or refused by the Portal's host and the kind of failure only, never the address or the secret, and a redirect is never followed.
- The Portal stores a Module's name and address only, never a credential (the database refuses an address with a user, password, query or fragment); the address and the Module's answers stay out of its logs.
- The Portal holds a Business's email and name: personal data. They stay out of logs and error messages (the audit log names an account id), and an invite or reset link is a credential: it only ever goes by email, and prints to the console only on a local run (`DEBUG=1`).
- A Business's call link (`Business.call_slug`) is a credential for starting calls on Petter's Google key, with one call at a time per Business and a daily budget in dollars (`Business.daily_budget_usd`, VOI-123) as the only limits: the dashboard shows it (inside the Call button snippet) only to that Business, and it never goes in a log the core writes.
- An Access token's secret (`voice_` and random characters) is shown once, on the Portal page that makes it, and never stored or logged: the database holds its SHA-256, and a log line names a token by its id (nothing logs one yet).
- The Call button snippet puts a Business's call slug in the HTML of that Business's own website: it is public by design. The Portal gives a ticket only to a request that says it is in a frame, and the core lets only the Business's saved website frame the page; neither stops a script that sends the header itself and opens the page in a tab (not enforced).
- Test fixtures use synthetic people only: generated names, +46 numbers we own or reserved test numbers, and personnummer that pass the checksum and are marked synthetic.
- Any real recording sits outside the repo.

## Enforced by

- Credentials in the repo: the `no-committed-secrets` guard.
- The Portal refuses to start without its secrets (`DJANGO_SECRET_KEY`, `CORE_SECRET`, `CORE_URL`) and mail settings outside a local run (`portal/settings.py`, `required`; `tests/portal/test_settings.py`).
- Personal data in logs, errors and fixtures, and real recordings: none yet, except the Live transcript: `tests/test_serve.py` fails if its words reach a log on their way to the page. The barge-in field list above: `tests/portal/test_call_logs.py` fails when it, the Call log contract's event fields and the database's `accounts_call_log_fields()` differ; the recorder's code is not checked against it, but a line with an unlisted field makes the Portal refuse that call's log (the core logs the give-up). The Call record field list: `tests/test_report.py` fails when a record or usage field is missing from it.
