# Gemini Live: voice, language code and getting the best out of the model

Read 2026-10-19 for VOI-156 and VOI-163. The question: does the language code (`sv-SE`) and voice name (`Charon`) the core sends make the agent sound less natural than the first demo, which sent neither? Widened the same day to Google's guidance for best results and to Swedish specifics.

Google's pages were read through a summarising fetch, so a quote below is the summary's wording, not checked against the page text; re-read a page before relying on an exact wording. Code was read as installed (Pipecat 1.12.0, google-genai 2.29.0, the versions in `uv.lock`) in the main checkout's `.venv`. Nothing here was heard: no call was made and no Gemini credit spent.

## Sources

- Pipecat 1.12.0, `pipecat/services/google/gemini_live/llm.py` (installed, read 2026-10-19), and `pipecat/transcriptions/language.py`.
- google-genai 2.29.0, `google/genai/types.py` (installed, read 2026-10-19): `SpeechConfig`, `LiveConnectConfig`, `AudioTranscriptionConfig`, `ProactivityConfig`.
- [Live API capabilities guide](https://ai.google.dev/gemini-api/docs/live-guide) (last updated 2026-09-18, read 2026-10-19), and the same content at [live-api/capabilities](https://ai.google.dev/gemini-api/docs/live-api/capabilities).
- [Live API best practices](https://ai.google.dev/gemini-api/docs/live-api/best-practices) (last updated 2026-09-15, read 2026-10-19).
- [Gemini 3.8 Live model page](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-live) (last updated 2026-10-19, read 2026-10-19).
- [Live API WebSockets reference](https://ai.google.dev/api/live) (last updated 2026-10-09, read 2026-10-19).
- [Live API session management](https://ai.google.dev/gemini-api/docs/live-session) (last updated 2026-09-15, read 2026-10-19).
- [Speech generation (TTS)](https://ai.google.dev/gemini-api/docs/speech-generation) (last updated 2026-10-12, read 2026-10-19).
- [Vertex AI: configure language and voice](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/live-api/configure-language-voice) (last updated 2026-10-15, read 2026-10-19).
- The first demo: `app/engine/gemini_live.py` and `app/prompts.py` in the archived repo `irma-AI/Voice-archive`, branch `claude/kind-ritchie-s52u3c` (last commit to the engine file 2026-09-27), read 2026-10-19 with `gh api`.
- Not primary, a signal only: a Google developer forum thread, [BUG: Gemini 3.8 Live API overrides language_code](https://discuss.ai.google.dev/t/bug-gemini-3-8-live-api-overrides-language-code-ignores-system-prompt-accent-formatting/185304) (opened 2026-09-27, read 2026-10-19; no reply from Google).

## 1. What the core sends today

`voice/agent.py` builds `GeminiLiveLLMService(settings=Settings(model=MODEL, system_instruction=..., language=Language.SV_SE, vad=VAD))`, with `MODEL = "models/gemini-3.8-live"` (`voice/cost.py`) and `VAD` = start sensitivity LOW, prefix padding 300 ms (`voice/bargein.py`). No voice is given.

Pipecat's `_connect` (llm.py lines 1316-1343) builds the setup as:

- `generation_config.speech_config.voice_config.prebuilt_voice_config.voice_name` = `"Charon"`: Pipecat's hard default (`voice="Charon"` in the service's default settings, line 671).
- `generation_config.speech_config.language_code` = `"sv-SE"`: the raw setting, passed as is (line 1336). Pipecat's own map to Gemini codes (`language_to_gemini_language`, lines 158-254) has no Swedish entry, so building the service logs `Language sv-SE not verified. Using 'sv-SE'.`; that mapped value is kept internally and is not what the setup sends.
- `generation_config.max_output_tokens` = 4096 and `response_modalities` = AUDIO (Pipecat defaults); temperature, top_p, top_k unset.
- `input_audio_transcription` and `output_audio_transcription` = empty configs (no language hints).
- `history_config.initial_history_in_client_content` = true, `session_resumption` set (Pipecat).
- `realtime_input_config.automatic_activity_detection`: start sensitivity LOW, prefix padding 300 ms; no silence duration, so the server default applies.
- No `thinking_config` (Pipecat adds a level only for model names with "thinking" in them, lines 472-531), no `enable_affective_dialog`, no `proactivity`, no context window compression.
- Pipecat adds nothing about voice or language to the system instruction. The only language words are the core's own: "Speak Swedish." plus, for two languages, "Answer in the language the caller last spoke: Swedish or English."

Checked offline (no call) by building the service and serialising `SpeechConfig` the way `_connect` does, 2026-10-19:

| `Settings(...)` | `speech_config` sent |
|---|---|
| `language=Language.SV_SE` (today) | `voice_name: Charon`, `language_code: sv-SE` |
| `language` left out | `voice_name: Charon`, `language_code: en-US` |
| `language=None` | `voice_name: Charon`, no `language_code` |
| `voice=None, language=None` | an empty `prebuilt_voice_config`, no `language_code` |

So leaving the language out is not enough: Pipecat then sends `en-US`. Only an explicit `language=None` leaves the field unset, and the setting's type (`Language | str | NotGiven`) does not admit `None`, so pyright will flag it. A voice can't be left unset the same way: `voice=None` still sends an empty `prebuilt_voice_config`, which is not what the demo sent (no `speech_config` at all); whether the server treats an empty one as "default voice" or refuses it: not checked.

## 2. What Google says about `language_code` on this model

- Gemini API capabilities guide: native audio output models "automatically choose the appropriate language and don't support explicitly setting the language code"; you can "restrict the languages it speaks in by specifying it in the system instructions."
- Vertex AI's page: "Live audio models like `gemini-3.8-live` can switch between languages naturally during conversation", and recommends "RESPOND IN LANGUAGE. YOU MUST RESPOND UNMISTAKABLY IN LANGUAGE." Its sample still sets `language_code="en-US"`, and its table of 24 language codes does not list `sv-SE` (Swedish is absent).
- The model page and the WebSockets reference say nothing about `language_code` (the reference does not describe `SpeechConfig` at all). The SDK only says "Optional. The language code (ISO 639-1) for the speech synthesis."
- Half-cascade: no page read mentions a half-cascade path for `gemini-3.8-live`, or that a language code switches the model to one. The model page lists only native audio output. Not checked further.
- Effect on naturalness: nothing documented. The API accepts the field (the core's calls run), so "not supported" seems to mean "not meant to be set", not "refused".
- Effect on switching: undocumented by Google. The forum thread reports that on `gemini-3.8-live` a non-US `language_code` made the model speak that language even when it should have spoken English, and that accent instructions were ignored. That is anecdote, but it points straight at the core's case: a Business with `["sv", "en"]` and the `language_switch` Scenario. Not checked by us.

Reading: Google's docs say not to set it for this model, the code we send is not in Google's Vertex list, and Pipecat flags it as unverified. Dropping it follows the docs. Whether it changes the sound: only the render (VOI-156) can tell.

## 3. Voices

The Live API accepts the 30 prebuilt TTS voices (capabilities guide: native audio models "support any of the voices available for our Text-to-Speech (TTS) models"; Vertex lists the same 30 for `voice_name`). Descriptors from the speech generation page:

Zephyr (Bright), Puck (Upbeat), Charon (Informative), Kore (Firm), Fenrir (Excitable), Leda (Youthful), Orus (Firm), Aoede (Breezy), Callirrhoe (Easy-going), Autonoe (Bright), Enceladus (Breathy), Iapetus (Clear), Umbriel (Easy-going), Algieba (Smooth), Despina (Smooth), Erinome (Clear), Algenib (Gravelly), Rasalgethi (Informative), Laomedeia (Upbeat), Achernar (Soft), Alnilam (Firm), Schedar (Even), Gacrux (Mature), Pulcherrima (Forward), Achird (Friendly), Zubenelgenubi (Casual), Vindemiatrix (Gentle), Sadachbia (Lively), Sadaltager (Knowledgeable), Sulafat (Warm).

- Default voice when none is sent: no page names one (examples use Kore). Not checked; the render's "no speech config" clip is the only way to hear it.
- Which voices sound good in Swedish: not documented. The pages don't say whether every voice speaks every language. The TTS page has an Extended Voice Library with regional accents and a BCP-47 voice filter; whether the Live API accepts those voices: not checked.
- Charon is "Informative": a newsreader descriptor, not a phone-receptionist one. Warm/friendly/casual candidates by descriptor: Sulafat, Achird, Zubenelgenubi, Callirrhoe, Aoede, Despina.

## 4. The first demo, and what else differs

From `app/engine/gemini_live.py` and `app/prompts.py` (archive, read 2026-10-19):

| | First demo | Core today |
|---|---|---|
| Model | `gemini-3.8-live` | `gemini-3.8-live` (same) |
| `speech_config` | none (no voice, no language code) | Charon, `sv-SE` |
| Transcription hints | input `language_codes: ["sv-SE", "en-US"]` | none |
| VAD | start LOW, prefix 300 ms, **silence 500 ms** | start LOW, prefix 300 ms, silence unset (server default "approximately 800ms") |
| Generation config | none | `max_output_tokens` 4096 |
| Thinking, affective dialog, proactivity | none sent | none sent |
| Audio | 16 kHz in, 24 kHz out | 16 kHz in, 24 kHz out (`voice/serve.py`) |
| Tools | BLOCKING declared | Pipecat declares synchronous tools BLOCKING |
| History, resumption | not set | Pipecat sets both |
| First turn | a text turn "Hälsa kort på svenska och fråga vad du kan hjälpa till med." | seed "The call has just connected."; prompt says start with exactly "Du pratar med en AI-assistent." |
| System prompt | ~960 characters, plus a knowledge outline | ~1,130 characters with the eval Business |

The prompts differ more than the settings. The demo's opens with a persona ("a friendly assistant on a voice call"), uses Google's "RESPOND ... UNMISTAKABLY IN SWEDISH OR ENGLISH" form, asks for informal "du", and says to "Talk like a person on the phone: short turns, contractions, the odd 'mm' or 'okej'". The core's has no persona and no tone instruction, caps turns at two sentences, and makes the model say several sentences word for word ("Say exactly"). Scripted sentences are read, not spoken, and a reply that starts with a fixed sentence tends to sound read; that is a guess, but a cheap one to hear.

Candidates for the "more natural" impression, most likely first (a judgement, none heard):

1. The prompt: the demo asked for phone-like speech; the core asks for rules and fixed sentences.
2. The end-of-speech silence: 500 ms against the server's ~800 ms, so the demo answered about 300 ms sooner. The demo's comment says 700 ms "felt slow".
3. The voice: the server's default against Charon ("Informative").
4. The language code: Google says not to set it; effect on sound unknown.

## 5. Recommendation for VOI-156's render

Hold everything else at today's core (same prompt, Business `tests/evals/business.json`, VAD, model), and change one thing per setup, so each clip answers one question:

| # | Setup | Question it answers |
|---|---|---|
| A | `sv-SE` + Charon (today) | baseline |
| B | no language code + Charon | does the language code change the sound? |
| C | no `speech_config` at all (the demo's) | the server's default voice |
| D1-D4 | no language code + Sulafat, Achird, Zubenelgenubi, Despina | voice choice |
| E | setup C + the demo's VAD silence (500 ms) and the demo's tone lines (persona, "talk like a person on the phone", "du") added to the prompt | how much of the gap is prompt and timing, not voice |

Each setup plays two Caller lines already rendered for the evals: `opening_hours_sv.wav` (a Swedish answer) and `switch_to_english_en.wav` (the switch, where the language code may bite). That is 8 setups, one short call each with two turns, so 8 calls and 8 clips (the disclosure, the Swedish answer and the English answer in each). Today's eval calls run about 2,000 to 3,600 tokens and 0.06 to 0.15 SEK each, so the render should cost about 0.5 to 1.5 SEK; even priced entirely at the audio-output rate in `tests/evals/prices.json` (3,600 tokens × $12/1M × 11 SEK/$ ≈ 0.48 SEK a call) it stays under 4 SEK, well inside the 10 SEK per-run cap in `tests/evals/caps.json`. Each clip is one sample of a random model: a second take of A and of the favourite is worth asking for if two clips sound close.

How to render without touching eval-required paths (`scripts/eval-required.json`): a new standalone script (for example `tests/evals/render_samples.py`, beside `render_audio.py`, with a `make voice-samples` target) that imports `system_instruction` and `VAD` from the core, builds `GeminiLiveLLMService` with the setup's settings, plays the two stored WAVs, and writes the agent's 24 kHz audio to a WAV per setup. Setup C can't be expressed through Pipecat's settings (see § 1), so either drive the session with google-genai directly for C, or accept Pipecat's empty voice config and say so. Setup E's prompt lines are added in the script only, never in `voice/agent.py`.

Where the clips go: they are synthetic agent speech, not a person, so no rule forbids keeping them, but they are not product either. Write them to the git-ignored `eval-runs/voice-samples/` (or the ticket's shared folder) and share them for listening, not commit them.

### Render results

Rendered by the Evals workflow with `target=voice-samples` after Petter's Approve ([run 39379261046](https://github.com/irma-AI/Voice/actions/runs/39379261046), 2026-10-20); the clips are that run's artifact, not committed. Figures from the run's log, one call per setup:

| # | Call length | Tokens | Cost |
|---|---|---|---|
| A | 22.9 s | 4,179 | 0.16 SEK |
| B | 18.9 s | 3,554 | 0.13 SEK |
| C | 20.1 s | 3,764 | 0.14 SEK |
| D1 | 18.7 s | 3,628 | 0.12 SEK |
| D2 | 17.9 s | 3,757 | 0.13 SEK |
| D3 | 20.2 s | 3,707 | 0.14 SEK |
| D4 | 19.1 s | 3,755 | 0.13 SEK |
| E | 16.7 s | 3,787 | 0.12 SEK |
| Total | | | 1.06 SEK |

Petter listened on 2026-10-20 and picked **E**: "clearly best" and "feels much snappier than the others". C, the same default voice without the 500 ms silence and the tone lines, did not stand out. So the gain comes from the silence duration and the tone lines more than from the voice; E is also the shortest call. Each clip is one sample; no second take was rendered.

What it implies: the next changes are timing and prompt, not the voice. VOI-178 carries the 500 ms silence and VOI-196 the prompt with the persona and tone lines; each is an eval-required change, so each needs a full paid `make eval` and Petter's go.

## 6. Google's guidance for best results, against `voice/agent.py`

| Topic | What Google says | Core today | Worth testing |
|---|---|---|---|
| System instruction | One agent per instruction; order persona, conversational rules, guardrails; "Keep your responses short and progressively disclose more"; "Instead of lengthy, multi-page prompts, consider using prompt chaining"; "unmistakably" for firm rules (best practices). Nothing on length and latency. | No persona; rules and guardrails mixed; ~1,130 characters, far from "multi-page". | Add a persona and a tone line; reorder into the three parts. Length is not the problem. |
| Output language | "RESPOND IN {OUTPUT_LANGUAGE}. YOU MUST RESPOND UNMISTAKABLY IN {OUTPUT_LANGUAGE}." (best practices, Vertex) | "Speak Swedish." | Use Google's form, for one or several languages. |
| Language code | Not supported on native audio; set language in the instruction (§ 2). | `sv-SE` | Drop it (`language=None`). |
| Affective dialog | Removed from the API for `gemini-3.8-live`: "Remove any `enable_affective_dialog` configurations" (model page). | Not sent. | Nothing to do. |
| Proactive audio | "Permanently enabled" on `gemini-3.8-live`; `proactive_audio: false` errors; with it on, the API "charges for input tokens the entire time the Live API is listening" (model page, best practices). | Not sent (it is on anyway). | Nothing to set; the cost note matters for call caps. |
| Thinking | `gemini-3.8-live` has interleaved reasoning; `thinkingLevel` "is not supported and must be omitted" (capabilities guide). | Omitted. | Nothing to do. |
| VAD and barge-in | Server VAD on by default; silence duration "Recommended (500ms–800ms)", server default "approximately 800ms"; start and end sensitivity default HIGH (reference). | Start LOW, prefix 300 ms, silence unset. | Silence 500-600 ms (the demo's value) for faster replies; watch the noise and speech barge-in Scenarios and Swedish mid-sentence pauses ("alltså…"). |
| Audio | 16-bit PCM; input natively 16 kHz; output always 24 kHz; send 20-40 ms chunks, don't buffer (best practices). | 16 kHz in, 24 kHz out. Chunk size: not checked. | Check the browser page's chunk size. |
| Session length | Audio-only sessions 15 minutes without compression; a connection lasts about 10 minutes; resumption handles valid 2 h; use `ContextWindowCompressionConfig` for long sessions (session page, best practices). Context window 128k tokens for native audio. | No compression; Pipecat sets resumption. | Only if calls near 10-15 minutes are expected. |
| Temperature and other generation settings | Nothing Google-specific for voice agents found. | Unset (model defaults). | No change without a reason. |
| Tools | "Be specific", say when to call, "performs best on tasks with single function calls"; NON_BLOCKING is now the default on 3.8 (model page). | Covered by VOI-142 (`gemini-live-tool-prompting.md`). | Nothing new. |
| Transcription | `language_codes` are hints for the input transcript; empty means auto-detect (reference, SDK). | Empty. | Hints `sv-SE`, `en-US` per the Business's languages (transcript quality only; whether the model's understanding uses them: not checked). |

Every change in the agent's prompt or settings is an eval-required change: a ticket, a full paid `make eval`, Petter's go and the `evals-approved` label.

## 7. Swedish

Documented:

- The Live API lists Swedish (`sv`) among the 99 languages it detects and speaks (capabilities guide). No quality tier or per-language rating is given.
- Vertex's language-code table does not list `sv-SE` (§ 2).
- No voice is documented as Swedish-specific or as better in Swedish.
- TTS: Swedish is marked supported for Gemini 3.8 Flash TTS and not for Gemini 3.8 Flash-Lite TTS (speech generation page). `tests/evals/render_audio.py` rendered the stored Swedish Caller lines with `gemini-3.8-flash-lite-tts`, which by Google's table does not support Swedish; VOI-212 switched it to `gemini-3.8-flash-tts` (table re-read 2026-10-20, page last updated 2026-10-12), and the stored audio is re-rendered by one `make eval-audio`.

Not documented by Google for the Live model (searched the pages above; none covers it): how it reads numbers, prices and "kr", times and opening hours ("08-17", "måndag-torsdag"), dates, phone numbers, postcodes ("123 45"), personnummer-like strings, addresses, English loanwords and mid-sentence code-switching, or "du" against "ni". Only anecdote exists, so each is a Scenario to propose, not a fact:

- Prices: "Vad kostar en undersökning?" against `950 kr`: the reply says "niohundrafemtio kronor", not "nio fem noll k r" (the eval Business already has the prices).
- Opening hours: "Har ni öppet på fredag?": the reply says "åtta till två" or "åtta till fjorton", not "noll åtta streck fjorton".
- Address: "Var ligger ni?": the street and number read naturally, the postcode as "ett två tre fyra fem" or "etthundratjugotre fyrtiofem", never letters.
- Phone numbers: a Business phone number in the facts read in Swedish groups (needs a number we own or a reserved test number, `.claude/rules/security.md`).
- Code-switching: a Swedish question with an English brand or loanword: the reply stays Swedish.
- "du" or "ni": the core's prompt says neither, though callers say "har ni"; decide the register (a wording choice for callers, so Petter's) and check it in a Scenario.

Whether the instruction's language matters: the pages don't say which language to write the system instruction in. The core's is English with Swedish fixed sentences; the demo's was the same. Not checked.

## Not checked

- The default voice when none is sent, and whether an empty `prebuilt_voice_config` is accepted.
- Any effect of `language_code` on sound or switching on `gemini-3.8-live` (only a forum report).
- Whether the Live API accepts Extended Voice Library voices.
- The browser page's input chunk size.
- Every quote above is a summarising fetch's, not the page text.
