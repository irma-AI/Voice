# Architecture

The map an agent needs before changing structure: the layers, which way dependencies point, and the one interface each cross-cutting concern goes through. Be strict about these boundaries and loose about how code inside a layer is written.

## Layers

Lowest first:

- **Call record** (`voice/record.py`): writes what happened on a call to a JSONL file. Used on the eval Channel only.
- **Barge-in** (`voice/bargein.py`): the Gemini detector settings (`VAD`) and `BargeInRecorder`, which writes a timings-only event for every barge-in. Used by the Agent on every Channel.
- **Agent** (`voice/agent.py`, `voice/business.txt`): the prompt, the disclosure line, the Business's facts, the Gemini Live service and the pipeline. `run_call(transport)` is the one way a call runs.
- **Channel**: turns a connection into a Pipecat transport and hands it to `run_call`. `voice/serve.py` is the web Channel (one page and a WebSocket, what `make up` and the Dockerfile run); `voice/web.py` is Pipecat's runner, kept for the eval Channel only. A phone Channel will sit beside them.

The **Portal** (`portal/`, ADR 0002) is a second service beside these layers: a Django app with its own Postgres where a Business logs in. It does not import `voice/`, and `voice/` never imports it or reads its database; the core can ask it for a Business's settings over a web address (VOI-24, VOI-25) but does not depend on it: the Portal is one adapter behind the core's settings port (ADR 0002, update 2026-10-14). Inside it: `portal/accounts/models.py` (the database rules) is under `invite.py` and the views, which sit under the URLs; nothing imports upward.

`tests/evals/` is outside the layers. It starts the web Channel on Pipecat's eval transport and imports `BUSINESS` and `DISCLOSURE` from the agent, so those facts keep one home.

## Dependency direction

Dependencies point down the list: Channel imports Agent, Agent imports Barge-in and Call record, nothing imports upward. Not enforced yet: `scripts/checks/layers.json` does not exist, so the `layers` guard is off (`DECISIONS.md`). When it exists, a layer may import only the layers its `may_import` names, and the guard fails any other import.

## Cross-cutting concerns

Each concern has one interface, and code reaches it only through that interface:

- **Secrets and settings**: environment variables, listed in `.env.example`; `GOOGLE_API_KEY` is read in `run_call` and checked up front in `voice/serve.py` and `voice/web.py`.
- **Auth for the web Channel**: `voice.auth.BasicAuth`, the one login in front of every route: the Basic login, or the cookie the page sets after it, because browsers don't reliably send the Basic login on a WebSocket (`voice/serve.py` adds it; it needs `VOICE_PASSWORD`, and `/ws` also accepts only its own site as Origin).
- **Ports of the core** (ADR 0002, update 2026-10-14): the core is a hub with lines in, each with one interface and one adapter for now. Channel (web, eval; phone later) and model are Pipecat's own transports and services. Settings (VOI-25): the Portal's address, or a file in the settings shape chosen explicitly for evals and local runs; none configured is a logged start that refuses calls with a spoken reason, and a Portal that is configured but down refuses too. Actions (VOI-27): Modules over MCP. Call reports (VOI-30): to the Portal, never blocking a call. A new line in is a new adapter behind a port, never a change to the call logic. The Portal and the core depend on the settings shape (VOI-24), never on each other; Modules depend on neither.
- **Portal accounts**: `portal.accounts.models.Account` is the only login (`AUTH_USER_MODEL`); a Business is a `Business` row pointing at its Account. `portal.accounts.invite.invite` is the one way the app creates them and sends an invite, called by the `invite_business` command; there is no sign-up page. Nothing stops other code from creating an Account (not enforced yet).
- **Business settings shape**: `contract/business-settings.schema.json` is the one definition of what the Portal tells the core. The Portal serves it from `Business.as_settings` at `GET /api/settings/<business id>/`, which wants the shared secret (`CORE_SECRET`) as a Bearer token; `tests/portal/test_settings_contract.py` fails when the model, the form or the schema drifts and names the side to edit. The AI notice is not in it.
- **Portal settings**: `portal/settings.py`, from environment variables listed in `.env.example`; outside a local run (`DEBUG` off) a missing value stops the Portal.
- **Logging**: Pipecat's loguru logger; `run_call` caps it at INFO so transcripts stay out of logs (`.claude/rules/security.md`).
- **Barge-in log**: `BargeInRecorder`, the only writer of the events `config`, `bot_speech`, `barge_in`, `caller_words`, `resumed` and `end`, one JSON line each with the call id and seconds since the call began. In production a line goes to the server log at INFO, prefixed `barge-in`; on the eval Channel the same line also lands in the call's JSONL file. A production line may hold only the fields in `.claude/rules/security.md`.
- **Call record**: `CallRecorder`, passed to `run_call` as `record_to`, set only on the eval transport.
- **AI disclosure**: `DISCLOSURE` in `voice/agent.py`.
- **Business facts**: `BUSINESS` in `voice/agent.py`, read from `voice/business.txt`.

No feature flags exist yet; the barge-in log is the only telemetry.
