---
paths:
  - "**/*.py"
  - ".env.example"
---

# Security and personal data

- API keys and carrier credentials come from the environment only; never logged, never in fixtures.
- Call audio, transcripts, phone numbers and names never appear in logs or error messages; log call IDs instead.
- The barge-in log (`voice/bargein.py`) is timings and levels only. A production line may hold: `t`, `call`, `e`, and per event `vad`; `phase`, `played_ms`; `bot_speaking`, `bot_ms`, `peak_dbfs`, `rms_dbfs`, `src`; `words`, `after_barge_in_ms`; `reason`, `secs`. A new field is added here first.
- Test fixtures use synthetic people only: generated names, +46 numbers we own or reserved test numbers, and personnummer that pass the checksum and are marked synthetic.
- Any real recording sits outside the repo.

## Enforced by

- Credentials in the repo: the `no-committed-secrets` guard.
- Personal data in logs, errors and fixtures, and real recordings: none yet. The barge-in field list above: none yet (the recorder's code is the only other copy of it).
