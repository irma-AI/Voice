# Voice

The voice core: it connects a phone or browser call to a live AI voice model and runs the call.

Nothing is built yet; decisions land in `DECISIONS.md` and `docs/adr/` as they are made. Agent setup: `CLAUDE.md`. Terms: `CONTEXT.md`. Commands: `make help`.

The web Channel (`make up`) sits behind one shared login: set `VOICE_PASSWORD` (and optionally `VOICE_USER`, default `voice`); it refuses to start without it. The `Dockerfile` is what Dokploy builds from `main`.
