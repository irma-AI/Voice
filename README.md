# Voice

The voice core: it connects a phone or browser call to a live AI voice model and runs the call.

A browser call to a live voice agent runs with `make up`; `make eval` plays the test calls. Decisions land in `DECISIONS.md` and `docs/adr/` as they are made. Agent setup: `CLAUDE.md`. Terms: `CONTEXT.md`. Commands: `make help`.

The web Channel (`make up`, `voice/serve.py`) streams the microphone over a WebSocket and sits behind one shared login: set `VOICE_PASSWORD` (and optionally `VOICE_USER`, default `voice`); it refuses to start without it. The `Dockerfile` is what Dokploy builds from `main`; its last stage builds the core, and its `portal` stage the Portal (self-hosting). The Portal, where a Business logs in, is `portal/` (`make portal-up`, Docker for its Postgres); Dokploy builds it from `main` with `Dockerfile.portal` (the production image, gunicorn) as app `portal`, next to a Postgres `portal-db`, at https://voice.petterannerwall.se; the call page (the Dockerfile's core, app `app`) is at https://call.petterannerwall.se.

## Self-host

The core, the Portal and Postgres on one machine, with your own Google key. Needs Docker only.

1. Download this repo and `cp .env.example .env`. In `.env`, put your Gemini key (aistudio.google.com) after `GOOGLE_API_KEY=`. Calls cost you, not anyone else. Change `VOICE_PASSWORD` and `CORE_SECRET` from `local` if other people use the machine.
2. Start everything: `docker compose -f compose.self-host.yml up --build` (or `make self-host`). The Portal is at http://localhost:8000 and the call page at http://localhost:7860; both listen on this machine only.
3. In a second terminal, invite yourself. It prints a plan first; run it again with the hash it shows:
   `docker compose -f compose.self-host.yml exec portal python -m django invite_business you@example.com "Your Business" --target local`
   `docker compose -f compose.self-host.yml exec portal python -m django invite_business you@example.com "Your Business" --target local --execute --approved-hash=<sha256>`
4. The invite email prints in that second command's output (no mail server is set up). Open the link in it; where a line ends in `=` and the text goes on below, join the lines without the `=`. Set a password, log in, and press the test call button.

The first Business invited is the one the shared call page serves. Your data stays in a Docker volume across `make self-host-down`. The Portal runs in its local mode here (Django's dev server, mail printed to the log): fine on one machine, not for a public address, where it needs the production values listed in `.env.example`. Not checked: a full call from the self-hosted copy (it spends Gemini credit); the steps were run from an empty folder up to the Portal handing the core a signed test-call ticket and the core reading the Business's settings from the Portal.
