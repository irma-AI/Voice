# False barge-in on noisy phone audio, and what to log

Researched 2026-10-13 for Petter. Research only: no code changed. Sources: pipecat-ai 1.12.0 wheel read in a scratch venv (`pipecat/...` paths below are inside it), google-genai and openai SDK type docs (generated from the vendors' API specs), vendor doc pages.
Legend: **[S]** read in source or official doc. **[I]** my inference. **[?]** not checked.

## Summary

- **Gemini decides, so Pipecat's VAD, min-words and volume knobs do nothing today.** Voice sets no `vad_analyzer` (`voice/agent.py`, `voice/serve.py`), so Gemini's server-side VAD is the only thing that ends the model's sentence. Pipecat then only reacts: Gemini says `interrupted`, the service broadcasts an `InterruptionFrame` (`services/google/gemini_live/llm.py:1498-1510`). **[S]**
- **Gemini has two knobs, OpenAI has more.** Gemini: start/end sensitivity (HIGH or LOW only), `prefix_padding_ms`, `silence_duration_ms`, and `activityHandling`. OpenAI adds a numeric `threshold`, `semantic_vad`, `interrupt_response` and a noise-reduction setting. Gemini has no volume or confidence threshold. **[S]**
- **Start sensitivity defaults to HIGH for Gemini Live.** That fits the symptom (noise cuts the model off). Setting LOW is the cheapest first try. Pipecat exposes it as `GeminiVADParams`, but **not** `activityHandling` (no match in `pipecat/`). **[S]**
- **We cannot see why an interruption happened.** `InterruptionFrame` carries no fields. Gemini sends no user-speech frames, so Pipecat's speaking, turn and latency observers are blind to the caller. The log has to be built from frames we can see plus a small energy measure of our own. **[S]/[I]**
- **Built-in gates that do work with server VAD:** an audio input filter on the transport, and `AlwaysUserMuteStrategy` (drops caller audio to the model while the bot speaks, so no barge-in at all). **[S]**
- **Recommendation (section 6):** A, tune server VAD, plus the interruption log, first. Gate (B) and noise filter (C) only once the log shows what the false interruptions look like.

## 1. How speech-to-speech models handle barge-in

**Gemini Live** (`google/genai/types.py` v2.30.1 docstrings; https://ai.google.dev/api/live; https://ai.google.dev/gemini-api/docs/live-api/capabilities) **[S]**
- `realtimeInputConfig.automaticActivityDetection`: `startOfSpeechSensitivity`, `endOfSpeechSensitivity` (HIGH/LOW; default HIGH for Gemini Live), `prefixPaddingMs`, `silenceDurationMs` (capabilities page: about 800 ms default, 500-800 ms suggested), `disabled`.
- The two pages disagree on `prefixPaddingMs`. The API reference says it is the speech duration required before start is committed, "lower ... more sensitive ... more false positives". The capabilities page calls it audio included before speech. The reference is the field spec, so raising it should cut short noises **[I]**; test it.
- `disabled: true`: the client detects speech and sends `activityStart`/`activityEnd`; the capabilities page advises at least 500 ms end-silence. These can only be sent with automatic detection off.
- `activityHandling`: `START_OF_ACTIVITY_INTERRUPTS` (default, "barge in") or `NO_INTERRUPTION`. `turnCoverage` default depends on the model (API reference).
- On interruption "the ongoing generation is canceled and discarded"; only what was already sent to the client stays in the session history; the server sends `serverContent.interrupted` and the client should clear its playback queue. The model cannot "resume" by itself; it answers the next turn.
- Not documented on the pages I read: noise, echo, headphones, a volume threshold. **[S]**

**OpenAI Realtime** (`openai/types/realtime/*` v3.29.0) **[S]**
- `server_vad`: `threshold` (default 0.5; "higher ... better in noisy environments"), `prefix_padding_ms` (300), `silence_duration_ms` (500), `interrupt_response`, `create_response`, `idle_timeout_ms`.
- `semantic_vad`: `eagerness` low/medium/high (max wait 8/4/2 s), `interrupt_response`, `create_response`.
- `audio.input.noise_reduction` (`near_field` or `far_field`) filters audio "before it is sent to VAD and the model ... reducing false positives".
- `interrupt_response: true` cancels the running response; the client then sends `conversation.item.truncate` so the server keeps only the audio actually played and deletes the unplayed transcript.

## 2. What Pipecat 1.12.0 offers, and what applies with Gemini server VAD

| Mechanism | Where | Applies today? |
|---|---|---|
| `GeminiVADParams` (disabled, start/end sensitivity, prefix_padding_ms, silence_duration_ms), `turn_coverage` | `GeminiLiveLLMService.Settings(vad=...)`, `llm.py:285-300, 1385-1424` | **Yes.** The only built-in barge-in knobs. Sent in the session setup, so a change needs a new session. `activityHandling` is not exposed; setting it means subclassing or patching the service **[I]**. |
| Silero VAD (`SileroVADAnalyzer`, `VADParams`: confidence 0.7, start_secs 0.2, stop_secs 0.2, min_volume 0.6; speech = confidence AND volume over threshold) | `LLMUserAggregatorParams(vad_analyzer=...)`, `audio/vad/vad_analyzer.py`, `llm_response_universal.py:184, 767` | **No**, nothing is wired. Only drives turns if Gemini's VAD is disabled (`examples/realtime/realtime-gemini-live-locally-driven-turns.py`: `vad=GeminiVADParams(disabled=True)`, `stop_secs=0.5`). Its docstring: local turn boundaries "are a heuristic and may not match" Gemini's. Model is bundled; `onnxruntime` is a core dependency; MIT per its GitHub page; supports 8 and 16 kHz only. |
| Turn start strategies: `VADUserTurnStartStrategy`, `MinWordsUserTurnStartStrategy` (word gate applies only while the bot speaks), `TranscriptionUserTurnStartStrategy`, `WakePhrase...` | `turns/user_start/`, `user_turn_strategies.py` | **No.** They fire on local VAD or transcripts. Realtime mode drops the transcription strategy (`llm_response_universal.py:954-998`). MinWords would need transcripts, which Gemini only produces after it has heard the audio **[I]**. |
| User mute strategies (`AlwaysUserMuteStrategy` etc.) | `LLMUserAggregatorParams.user_mute_strategies`, `llm_response_universal.py:1208-1252` | **Yes, blunt.** While muted the aggregator drops `InputAudioRawFrame`, so Gemini hears nothing: half-duplex, no barge-in. |
| Audio input filter | `TransportParams.audio_in_filter`, runs in `transports/base_input.py:284` before frames enter the pipeline | **Yes.** |
| Custom `FrameProcessor` before the model | `transport.input() -> [here] -> user -> llm` | **Yes.** Can pass, attenuate or replace caller audio. Gemini's VAD needs a continuous stream (`llm.py:1732`), so replace with zeros, do not drop **[I]**. |

**Audio filters shipped in 1.12.0** (`pipecat/audio/filters/`) **[S]**: `RNNoiseFilter` (extra `rnnoise` = `pyrnnoise` + `av`; RNNoise needs 48 kHz so the filter resamples both ways; pyrnnoise is Apache-2.0 per its GitHub page; RNNoise's own licence [?]), `KrispVivaFilter` (Krisp SDK licence + API key + `.kef` model; 8-48 kHz; docs: https://docs.pipecat.ai/api-reference/server/utilities/audio/krisp-viva-filter), `AICFilter` (ai-coustics `license_key`, model download), `KoalaFilter` (Picovoice `access_key`). The last three are vendors; prices [?].

**Frames.** `InterruptionFrame` has no fields (`frames/frames.py:1221`). With server VAD the only source is the LLM service; it is broadcast both ways, and the output transport clears queued audio (`transports/base_output.py:575`). Our WebSocket serializer turns it into `{"type":"interrupt"}` (`voice/serve.py`). The service docstring (`llm.py:411-427`) says Gemini Live does **not** emit `UserStartedSpeakingFrame`/`UserStoppedSpeakingFrame` or the `VADUser...` frames. So `SpeakingObserver`, `TurnTrackingObserver` and `UserBotLatencyObserver` get no user events **[I, from their imports]**. Bot-side frames still flow: `BotStarted/StoppedSpeakingFrame` (output transport), `LLMFullResponseStartFrame`, `TTSTextFrame`, `TranscriptionFrame` (upstream, late). In the eval, RTVI turns `InterruptionFrame` into `bot-interrupted` (`processors/frameworks/rtvi/observer.py:480`).

## 3. Common practice for noisy phone audio (sourced only)

- **Loudness/confidence gate:** Pipecat's VAD requires both confidence and smoothed volume (`vad_analyzer.py`); OpenAI documents a higher `threshold` for noisy rooms. Gemini offers neither.
- **Minimum duration:** Gemini `prefixPaddingMs` (above); Pipecat `start_secs`.
- **Minimum words, only while the bot speaks:** Pipecat's `MinWordsUserTurnStartStrategy` (docs: https://docs.pipecat.ai/server/utilities/turn-management/user-turn-strategies).
- **Suppress noise before VAD:** OpenAI's `noise_reduction` is applied before VAD; Pipecat's filter also runs before any VAD.
- **Echo/speaker bleed:** our page already requests `echoCancellation` and `noiseSuppression` (`voice/page.html:66`). Whether browser AEC covers our Web Audio playback is [?]. Krisp's filter has a TTS-detection model "to delay voice isolation until bot speech playback has stopped" (`krisp_viva_filter.py` docstring), a sign the vendor sees filter/bot-audio interaction.
- **Telephony:** Pipecat's Twilio serializer defaults to 8 kHz µ-law (`serializers/twilio.py:73-79`); Gemini wants 16 kHz in (https://ai.google.dev/gemini-api/docs/live-api/best-practices), so a phone call is upsampled narrowband audio **[I]**. Silero (8 kHz: 256-sample frames) and Krisp take 8 kHz; RNNoise resamples to 48 kHz. No phone Channel exists yet, so this is not what Petter hears today **[S: ARCHITECTURE.md]**. "On a phone" may mean the browser page on a phone; worth confirming.

## 4. Monitoring

**What Pipecat gives (1.12.0).** `MetricsFrame` with `TTFBMetricsData`, `TTFAMetricsData`, `ProcessingMetricsData`, `LLMUsageMetricsData` (prompt/completion/audio tokens), `TurnMetricsData` (`metrics/metrics.py`); `agent.py` already enables metrics and usage. Observers (`pipecat/observers/`): `SpeakingObserver` (user speech, turn, bot speech, `INTERRUPTION` as separate records), `UserBotLatencyObserver`, `TurnTrackingObserver`, `FunctionCallObserver` (started/in_progress/completed/failed/timed_out/cancelled, with `started_at`, `in_progress_at`), `ServiceMetricsObserver`, `ErrorObserver`. OpenTelemetry via extra `tracing` and `PipelineParams(enable_tracing=True)`; Gemini Live methods are traced (`traced_gemini_live`: setup, response, tool_call, tool_result). Tracing is built on turn tracking, so it is likely empty without user turn frames **[I]**; an exporter is a service, so a vendor unless it is a file or console exporter.
**Gap with server VAD:** Gemini's TTFB timer starts only at `UserStoppedSpeakingFrame` or when context is first set (`llm.py:985, 1921, 1966`), so our `ttfb` events probably cover only the opening greeting **[I]**.

**Per interruption, facts to log:** time; whether the bot was speaking and for how long; caller-audio loudness just before (peak and RMS dBFS over the last 500 ms, computed by us from `InputAudioRawFrame`); active settings; the next caller transcript (word count only), its delay, and whether and when the model started speaking again. The routine decides what is "false"; a policy baked into the record can never be revised (`SpeakingObserver` docstring says the same).

**Privacy.** `.claude/rules/security.md`: no transcripts in logs, call ID not numbers. `CallRecorder` writes text and runs on the eval Channel only. A production log must hold no text. Where it is stored and kept is Petter's call (CLAUDE.md: real calls and people).

**Minimal JSONL schema** (same shape as `CallRecorder`: `t` seconds since start, `e` name; new events only):

| `e` | fields |
|---|---|
| `config` | `vad` (start, end, prefix_ms, silence_ms, disabled), `gate` (name, params), `in_rate`, `build` |
| `bot_speech` | `phase` (start/stop), `played_ms` on stop |
| `interrupt` | `bot_speaking`, `bot_ms`, `peak_dbfs`, `rms_dbfs`, `src` (gemini/gate) |
| `caller` | `words` (production), `text` (eval only), `after_interrupt_ms` |
| `resumed` | `after_interrupt_ms` (next `agent_start`) |
| `gate` | `action` (pass/silence/drop), `reason`, `rms_dbfs`, `bot_speaking` (only if a gate exists) |
| `reply` | `after_loud_ms` (last loud caller frame to first agent audio; approximate) |
| `tool` | `name`, `id`, `phase` (start/progress/done/failed/timeout/cancelled), `ms`, `blocking` |
| `usage` | unchanged (token buckets incl. audio) |
| `end` | `reason`, `secs` |

**Later, not MVP (research only):** shadow Silero VAD for exact speech start/stop and confidence (as logging only; its default start strategy would also fire interruptions, so it needs inert strategies **[I]**); echo estimate (caller-audio correlation with bot audio); per-call interruption rate and share of one-word or no-transcript interruptions; speech overlap duration; noise floor per call; model audio played before cut; session-resumption and `goAway` events; STT-vs-model transcript disagreement; per-tool timeout rate; OpenTelemetry export; cost per call by token bucket; first-word clipping after a gate.

## 5. Testing

**Free (`make test`, seam 2).** Today a record is a list of turns (`tests/calls/*.json`, `Call.load`). A barge-in check needs events, which `read_events` already parses from JSONL. Pure function `false_interrupts(events) -> Verdict`: fail if an `interrupt` while `bot_speaking` has no `caller` with at least 2 words within N s and `peak_dbfs` is under a limit. One stored passing and one failing synthetic record, like the others. CLAUDE.md § Tests says a new seam needs a `/grill-with-docs` update first. A gate's decision function can be tested the same way (inputs: loudness, bot_speaking, params; output: pass/silence).

**Paid eval (`make eval`, ask Petter).** Scenario: after `bot_started_speaking`, a turn with `send_after: {event: llm_started, delay_ms: ~1500}` plays a noise-only WAV (`user:` text is required by the harness, `audio:` is the file). Expect `bot_interrupted` with `absent: true, within_ms: ...` and `bot_stopped_speaking` (`pipecat/evals/script.py` docs, `absent` and `send_after`). A twin Scenario with real speech must still produce `bot_interrupted`. Noise comes from synthetic sources (generated pink/white noise, babble mixed from our own TTS clips; no real recordings, `security.md`), mixed offline with numpy and optionally downsampled to 8 kHz and back to mimic a phone line.

**Limits of the eval transport** (`evals/client_transport.py:248-258`, `evals/audio.py`) **[S]**: idle caller audio is exact digital silence, so there is no ambient noise floor between turns; one WAV per turn, so no continuous background noise under the whole call; the bot's audio is never fed back, so echo cannot be tested; one run gives a pass or fail on a non-deterministic server VAD, not a rate **[I]**, so a rate needs repeats and credit. Synthetic noise is not proven to resemble the real noise that caused the problem [?].

## 6. Options for the MVP

| | A: tune Gemini VAD + log | B: Pipecat-side gate | C: noise filter |
|---|---|---|---|
| What | `GeminiVADParams(start_sensitivity=LOW, raise prefix_padding_ms; maybe end_sensitivity, silence_duration_ms)` in `agent.py`, plus a `FrameProcessor` writing the section 4 events | Processor before the model: while the bot speaks, replace caller audio below a loudness limit with zeros (or `AlwaysUserMuteStrategy` for full half-duplex); decision function logged as `gate` | `RNNoiseFilter` as `audio_in_filter` (or Krisp/AIC/Koala) |
| Needs | Edit `agent.py` (an eval-required path: full paid `make eval` receipt); new module in the core; a decision on where production logs go | Thresholds, which need A's log; custom code | Extra `rnnoise` (+ `av`); 48 kHz resample cost; tuning for 8 kHz [?] |
| Risk | Knobs unproven on `gemini-3.8-live` [?]; LOW start may clip a quiet caller's first word; no loudness threshold | Swallows real interruptions and the first words of a quiet caller; half-duplex feels stiff | Filter artifacts can hurt recognition; on the web page the browser already filters |
| Vendor / spend | None. Eval credit for the receipt | None. Eval credit | RNNoise: none (new dependency). Krisp, AIC, Koala: **new vendor and licence, Petter decides**, prices [?] |

**D (later): local Silero VAD drives turns** (`disabled=True`). Most control, but turn boundaries become heuristic and `agent.py` is rewired. Not for the MVP.

**Recommendation: A, in two steps.** (1) The log alone first, to get a baseline of how many interruptions have no transcript (rule 7: seen to hold before claimed). (2) Then change start sensitivity and padding, and compare the log. Build B as a decision function only if the log shows loud-enough noise passing the server VAD; build C when the phone Channel arrives, starting with RNNoise since it adds no vendor. `DECISIONS.md` (2026-10-13) says to revisit the eval-required list "when barge-in settings live elsewhere". Moving the VAD settings to another file would take them out of the receipt guard even though they change what callers hear, so that is Petter's call, not a shortcut **[I]**.
