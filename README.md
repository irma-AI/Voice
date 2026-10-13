# Voice

The voice core: it connects a phone or browser call to a live AI voice model and runs the call.

A browser call to a live voice agent runs with `make up`; `make eval` plays the test calls. Decisions land in `DECISIONS.md` and `docs/adr/` as they are made. Agent setup: `CLAUDE.md`. Terms: `CONTEXT.md`. Commands: `make help`.

The web Channel (`make up`, `voice/serve.py`) streams the microphone over a WebSocket and sits behind one shared login: set `VOICE_PASSWORD` (and optionally `VOICE_USER`, default `voice`); it refuses to start without it. The `Dockerfile` is what Dokploy builds from `main`.
