# Architecture

The map an agent needs before changing structure: the layers, which way dependencies point, and the one interface each cross-cutting concern goes through. Be strict about these boundaries and loose about how code inside a layer is written.

## Layers

Lowest first:

- **Call record** (`voice/record.py`): writes what happened on a call to a JSONL file. Used on the eval Channel only.
- **Agent** (`voice/agent.py`, `voice/business.txt`): the prompt, the disclosure line, the Business's facts, the Gemini Live service and the pipeline. `run_call(transport)` is the one way a call runs.
- **Channel**: turns a connection into a Pipecat transport and hands it to `run_call`. `voice/serve.py` is the web Channel (one page and a WebSocket, what `make up` and the Dockerfile run); `voice/web.py` is Pipecat's runner, kept for the eval Channel only. A phone Channel will sit beside them.

`tests/evals/` is outside the layers. It starts the web Channel on Pipecat's eval transport and imports `BUSINESS` and `DISCLOSURE` from the agent, so those facts keep one home.

## Dependency direction

Dependencies point down the list: Channel imports Agent, Agent imports Call record, nothing imports upward. Not enforced yet: `scripts/checks/layers.json` does not exist, so the `layers` guard is off (`DECISIONS.md`). When it exists, a layer may import only the layers its `may_import` names, and the guard fails any other import.

## Cross-cutting concerns

Each concern has one interface, and code reaches it only through that interface:

- **Secrets and settings**: environment variables, listed in `.env.example`; `GOOGLE_API_KEY` is read in `run_call` and checked up front in `voice/serve.py` and `voice/web.py`.
- **Auth for the web Channel**: `voice.auth.BasicAuth`, the one login in front of every route (`voice/serve.py` adds it; it needs `VOICE_PASSWORD`, and `/ws` also accepts only its own site as Origin).
- **Logging**: Pipecat's loguru logger; `run_call` caps it at INFO so transcripts stay out of logs (`.claude/rules/security.md`).
- **Call record**: `CallRecorder`, passed to `run_call` as `record_to`, set only on the eval transport.
- **AI disclosure**: `DISCLOSURE` in `voice/agent.py`.
- **Business facts**: `BUSINESS` in `voice/agent.py`, read from `voice/business.txt`.

No feature flags or telemetry exist yet.
