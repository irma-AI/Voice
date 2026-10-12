# Pipecat for the M0 spike

Checked 2026-10-12 against pipecat-ai 1.12.0 (PyPI, released 2026-09-25) and the Gemini API model list for our key.

- **Gemini 3.8 Live is reachable.** `models/gemini-3.8-live` and `models/gemini-3.8-live-extended-thinking` are listed with `bidiGenerateContent` (Primary: `GET /v1beta/models` with our key). Pipecat's `GeminiLiveLLMService` supports both, including `NON_BLOCKING` function calls (Primary: Pipecat CHANGELOG, 1.11.0). Pipecat's default model is still `gemini-2.5-flash-native-audio-preview-12-2025`, so we set the model explicitly.
- **The browser page needs no code of ours.** The dev runner (`pipecat.runner.run.main`, extra `runner`) serves a prebuilt client at `http://localhost:7860/client` and redirects `/` there; with `-t webrtc` it uses the SmallWebRTC transport (extra `webrtc`) (Primary: `pipecat/runner/run.py`).
- **The eval transport ships in the release.** `pipecat.evals` is in the 1.12.0 wheel, with an eval transport (`EvalTransportParams`, a WebSocket speaking RTVI that can capture bot audio) and a `pipecat eval suite` CLI command (Primary: wheel contents; `pipecat/evals/transport.py`). A bot opts in by adding an `"eval"` entry to its transport params, so the same bot serves the browser and the eval channel. Not yet run by us against Gemini Live in audio mode.
- **Typing gap.** `pipecat.runner.utils.create_transport` takes a dict of untyped factories, which pyright strict flags; one ignore on the import.
