# How Pipecat bots with a browser client are usually deployed

Question (Petter, 2026-10-13): how is browser audio into a containerised Pipecat bot usually solved? Sources are Pipecat's own docs, its examples repo and its issue tracker, read 2026-10-13. Where a source says nothing, this note says so.

## What Pipecat says

1. **The runner we use is a development tool.** `voice.web` runs `pipecat.runner` (prebuilt page at `/client`, `POST /start`, `POST /api/offer`). Pipecat: the runner "is a local development tool — it isn't built or supported for production use. For anything real, put a proper dispatcher or a managed runtime in front of your bots" ([running bots locally](https://docs.pipecat.ai/pipecat/deployment/running-bots-locally)).
2. **Its `/start` is open to anyone.** "`POST /start` accepts session-start requests from anyone", there is "no rate limiting", and a request "can spin up a bot and create paid rooms on your account"; it advises not exposing the runner publicly, and names no auth mechanism ([deployment pattern](https://docs.pipecat.ai/deployment/pattern)). So our login in front of every route is needed, not extra.
3. **SmallWebRTC (our page) needs help leaving a local network.** ICE servers are "optional for local network development" but needed "as soon as peers are on different networks"; the table lists STUN as needed and TURN as recommended for production, and both for Docker without host networking (macOS case) ([SmallWebRTC server](https://docs.pipecat.ai/api-reference/server/services/transport/small-webrtc)). The runner takes them from `--ice-servers` or `PIPECAT_ICE_SERVERS` and hands them to the browser in the `/start` response (`pipecat/runner/run.py`, installed 1.12.0).
4. **A maintainer's answer to "remote clients can't connect"**: SmallWebRTC "is meant for local testing", remote clients need a TURN server, or a production transport such as Daily. The reporter later got a self-hosted coturn working ([pipecat issue 1570](https://github.com/pipecat-ai/pipecat/issues/1570)).
5. **The usual production answer is a hosted transport**: Daily (WebRTC, also behind Pipecat Cloud) or a telephony provider ([development runner guide](https://docs.pipecat.ai/api-reference/server/utilities/runner/guide), [session initialization](https://docs.pipecat.ai/pipecat/learn/session-initialization)). Daily is a new vendor, so a stop-and-ask item.
6. **WebSocket is supported but called a prototype transport.** Server: `FastAPIWebsocketTransport` with `ProtobufFrameSerializer`. Browser: `@pipecat-ai/websocket-transport` plus `@pipecat-ai/client-js`, default 16 kHz capture and 24 kHz playback ([JS transport](https://docs.pipecat.ai/client/js/transports/websocket)). Pipecat: "best suited for prototyping and controlled network environments" and it "strongly recommend[s]" WebRTC for client/server production apps ([websocket server](https://docs.pipecat.ai/server/services/transport/websocket-server)). It only restricts by `Origin` (`PIPECAT_ALLOWED_ORIGINS`), so auth is ours either way.

## Not found

- No Pipecat page gives the UDP ports a SmallWebRTC or TURN container needs, or an official Dockerfile for it. The deployment examples (Fly.io, Modal, AWS AgentCore) were listed by folder name only; their transports and Dockerfiles were not read.
- Whether Petter's Dokploy host allows inbound UDP: not checked.

## What it means for the choice

| Option | Fits Pipecat's advice | Cost here |
|---|---|---|
| Keep built-in page + relay (coturn) | Documented fix, self-hosted works per issue 1570 | Second Dokploy app; the relay itself needs UDP ports published (or TCP/TLS relay: unverified) |
| Keep built-in page + hosted transport (Daily) | The usual production answer | New vendor and cost |
| WebSocket with Pipecat's own browser client | Supported, but labelled prototype | No relay, no open ports; our own small page bundling the official client; phone Channels also stream over WebSocket |
