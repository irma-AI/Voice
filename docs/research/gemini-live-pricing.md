# Gemini Live pricing and usage reporting

Retrieved 2026-10-12. Question: what Google bills for `gemini-3.8-live`, how the Live API reports usage, how Pipecat 1.12.0 surfaces it.

## 1. Price, `gemini-3.8-live` (Standard, Paid Tier, USD per 1M tokens)

Source: https://ai.google.dev/gemini-api/docs/pricing (retrieved 2026-10-12). The page's row covers `gemini-3.8-live`, `gemini-3.8-live-extended-thinking` and `gemini-3.1-flash-live-preview` together. The values below were read through a page-to-markdown summarizer, not the raw HTML, so re-check them on the page before they feed a billing cap.

| Direction | Modality | USD / 1M tokens | Page also lists |
|---|---|---|---|
| Input | audio | 3.00 | $0.005/min |
| Input | text | 0.75 | |
| Input | image/video | 1.00 | $0.002/min |
| Output | audio | 12.00 | $0.018/min |
| Output | text | 4.50 | |
| Cached / context | any | none listed | |

- Cached/context rate: the page lists none for these models. Treat cached tokens as unverified; do not assume a discount.
- Free tier is "free of charge" for these models, so a free-tier key is not billed (the paid-tier rates above apply to a billed key only).
- Not verified: whether thinking tokens (`thoughtsTokenCount`) bill at the text-output or audio-output rate. The page row does not say.
- Comparison rows on the same page: `gemini-2.5-flash-native-audio-preview-12-2025` is $0.50 text / $3.00 audio in, $2.00 text / $12.00 audio out.

## 2. How the Live API reports usage

Source: https://ai.google.dev/api/live, `UsageMetadata` (retrieved 2026-10-12). It rides on server messages. All fields are output only.

- `promptTokenCount`: input total; includes cached tokens when cached content is used.
- `cachedContentTokenCount`: cached part of the prompt.
- `responseTokenCount`: combined across response candidates.
- `thoughtsTokenCount`: thinking tokens.
- `toolUsePromptTokenCount`: tool-use prompt tokens.
- `totalTokenCount`: prompt + response.
- Per-modality lists of `ModalityTokenCount`: `promptTokensDetails`, `cacheTokensDetails`, `responseTokensDetails`, `toolUsePromptTokensDetails`.
- `ModalityTokenCount` is not defined on the Live page; it points to the Generating content docs. Its fields (`modality`, `tokenCount`) are known from the SDK (pipecat imports it), not confirmed from the docs page here: unverified.
- Not verified: whether the counts are cumulative per session or per turn. Pipecat's own handler (below) treats each message as one usage report; check against a real call log before summing.

## 3. Pipecat 1.12.0 `GeminiLiveLLMService`

Source: `/home/user/Voice/.venv/lib/python3.13/site-packages/pipecat/services/google/gemini_live/llm.py`, `_handle_msg_usage_metadata` (about line 2394) and `_audio_token_count` (line 127).

It builds one `LLMTokenUsage` per usage message and calls `start_llm_usage_metrics`:

| `LLMTokenUsage` field | Filled from |
|---|---|
| `prompt_tokens` | `prompt_token_count` (or 0) |
| `completion_tokens` | `response_token_count` (or 0) |
| `total_tokens` | `total_token_count`, else prompt + completion |
| `cache_read_input_tokens` | `cached_content_token_count` |
| `reasoning_tokens` | `thoughts_token_count` |
| `input_audio_tokens` | AUDIO entry of `prompt_tokens_details` |
| `output_audio_tokens` | AUDIO entry of `response_tokens_details` |
| `cache_read_input_audio_tokens` | AUDIO entry of `cache_tokens_details` |

Per-modality: only the AUDIO count is kept. Text tokens are not stored. Derive them as total minus audio (input: `prompt_tokens - input_audio_tokens`; output: `completion_tokens - output_audio_tokens`). That remainder also contains image/video input and any other non-audio modality, so it overstates text if video is sent. `_audio_token_count` returns `None` when Gemini omits the list or the modality (it omits zero-token modalities). Treat `None` as 0 only after checking the list was absent for a reason, not because the call failed (fail closed). Tool-use token counts are dropped. `llm.py` line 1522 logs a warning when `turn_complete` arrives without usage metadata, so a missing report is detectable.

Cost formula that follows from the above (using section 1): `input_audio*3.00 + (prompt - input_audio)*0.75 + output_audio*12.00 + (completion - output_audio)*4.50`, per 1M tokens. Whether `completion_tokens` already includes thinking tokens is unverified.

## 4. USD to SEK source

Use the Riksbank's published exchange rates (Swedish central bank, SWEA open API at https://developer.api.riksbank.se, series SEKUSDPMI): unverified, I did not fetch it. A verified alternative: the ECB euro reference rates, https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/ . Its SEK page showed 11.1965 SEK per EUR on 2026-10-12 (retrieved 2026-10-12), but that is EUR-based; USD/SEK needs the ECB USD page too (EUR/USD not fetched). No rate is hardcoded here. Read the rate at run time and store its date with the number.
