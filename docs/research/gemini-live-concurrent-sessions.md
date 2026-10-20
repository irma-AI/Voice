# Gemini Live concurrent sessions

Read 2026-10-20. Question: how many Gemini Live sessions one API key may hold open at once, so `make eval` can play Scenarios side by side (VOI-209).

## Google's documents

- Gemini API rate limits, https://ai.google.dev/gemini-api/docs/rate-limits (page last updated 2026-10-15, read 2026-10-20): names RPM, TPM, RPD, IPM, TPD and a spend limit per 10 minutes; no concurrent-session limit. "Rate limits are applied per project, not per API key." Live values per model and tier are shown only in AI Studio (https://aistudio.google.com/rate-limit).
- Live API session management, https://ai.google.dev/gemini-api/docs/live-session (last updated 2026-09-15, read 2026-10-20): session length only (15 minutes for audio without compression); no concurrency limit.
- Live API overview, https://ai.google.dev/gemini-api/docs/live-api (last updated 2026-10-06, read 2026-10-20): no concurrency limit.
- Firebase AI Logic, Live API limits and specs, https://firebase.google.com/docs/ai-logic/live-api/limits-and-specs (last updated 2026-10-13, read 2026-10-20): the Live API is limited by concurrent sessions per project and by TPM; for the Gemini Developer API the limit "vary based on your project's ... usage tier" with no number; Vertex AI lists 1,000 concurrent sessions per project.

## Not official

- Google AI developer forum, https://discuss.ai.google.dev/t/official-concurrent-session-rps-limits-for-gemini-live-api-where-are-they-documented/174664 (read 2026-10-20): a reply (2026-07-13, not marked as Google staff) says concurrent sessions are not guaranteed and limits follow tokens per minute. Older posts mention a 3-session cap on the free tier.

## Answer

No document gives a number for our key: the limit is per Google project and tier, visible only in AI Studio (not checked: it needs Petter's login). The project is on the paid tier (DECISIONS.md, 2026-10-18). The lowest figure seen anywhere is 3 (free tier, forum), so `make eval` plays 3 at a time; a refused session shows as that Scenario's failed suite exit, not as a pass.
