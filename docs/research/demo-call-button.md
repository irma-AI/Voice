# A call button on our own landing page: a capped demo call

Read 2026-10-20. The question (Petter's idea, 2026-10-20): let a visitor to the landing page call our own agent, to show new customers what Voice does, without an open tap on Petter's Google key. MVP first; bigger options under § 8.

This file is research, not a decision: every number below is a proposal for Petter, and every caller-facing sentence is his (CLAUDE.md § Stop and ask).

## Sources

| Source | Link | Read |
|---|---|---|
| Gemini Developer API pricing, `gemini-3.8-live` row (page last updated 2026-10-19) | https://ai.google.dev/gemini-api/docs/pricing | 2026-10-20 |
| Live API best practices, cost and session length (last updated 2026-09-15) | https://ai.google.dev/gemini-api/docs/live-api/best-practices | 2026-10-20 |
| Live API session management (last updated 2026-09-15) | https://ai.google.dev/gemini-api/docs/live-session | 2026-10-20 |
| Gemini API billing: project spend caps, tier caps, prepaid credit (last updated 2026-09-28) | https://ai.google.dev/gemini-api/docs/billing | 2026-10-20 |
| Gemini API rate limits (last updated 2026-10-15) | https://ai.google.dev/gemini-api/docs/rate-limits | 2026-10-20 |
| Cloud Billing: create, edit or delete budgets and budget alerts (last updated 2026-10-13) | https://docs.cloud.google.com/billing/docs/how-to/budgets | 2026-10-20 |
| Django 6.1 cache framework, local-memory cache (the Portal pins Django 6.1.2 in `uv.lock`) | https://docs.djangoproject.com/en/6.1/topics/cache/ | 2026-10-20 |
| W3C Fetch Metadata Request Headers, Working Draft 21 September 2026 | https://www.w3.org/TR/fetch-metadata/ | 2026-10-20 |
| GDPR and IMY sources, as listed in `docs/research/call-log-legal-ground.md` § Sources | (that file) | 2026-10-19 |

Repo read on `main` at dff4502: `portal/accounts/views.py` (`home`, `showcase`, `to_core`, `spent_today`, `call_link`, `client_address`, `count_try`, `totals`), `portal/accounts/models.py` (`CALL_KINDS`, `BUDGET_COUNTED`, `DAILY_BUDGET_USD`), `portal/accounts/ticket.py`, `voice/ticket.py`, `voice/serve.py` (`MAX_CALL_SECS`, one call per Business), `voice/page.html`, `voice/settings.py`, `voice/cost.py`, `voice/agent.py` (`DISCLOSURE`), `tests/evals/caps.json`, `.claude/rules/security.md`, `DECISIONS.md`.

## 1. What exists today

- **Two ways into a call, both through `to_core`** (the one way in): the test call button (`test`, logged-in Business, budget-exempt) and the public call link `/call/<slug>/` (`call_link`), opened by the Call button script in a panel on a Business's website. Both mint a ticket `<business>.<kind>.<expiry>.<domain>.<hmac>` signed with `CORE_SECRET`, valid for `TTL_SECONDS = 600` and not single-use: the core checks signature and expiry only, so one ticket can open several calls, one after another, within those 10 minutes.
- **The call link already has the spend controls a demo needs:** a daily budget per Business in dollars (`Business.daily_budget_usd`, default `$10`, VOI-123; no Portal page sets it, and `0` refuses every call), checked in `to_core` before a ticket is minted, and one open call at a time per Business in the core (`voice/serve.py`, the `one_call` set; a second socket is closed with code 1008).
- **Call length:** one ceiling for every call, `MAX_CALL_SECS = 600` in `voice/serve.py`, passed to Pipecat as `session_timeout`. Not per Business, not per kind.
- **What a refused visitor reads:** a spent budget renders `call_link_refused.html` in the panel with Petter's approved sentence "Something went wrong. We can't take calls right now." (DECISIONS.md 2026-10-18, VOI-123). A second call while one is open: the socket closes and `voice/page.html` shows its normal end state ("Call ended", "Thank you for calling."), which is wrong for "busy".
- **Gaps that matter for a public button:**
  - `spent_today` counts an unpriced call "at nothing before the first priced call" (Petter, 2026-10-18). If the price lookup (`voice/cost.py`, `BILLING_API_KEY`) fails from the demo Business's first call, its budget never trips: a fail-open for this use.
  - `spent_today` counts closed calls only (a call may run over, the next is refused). With one call at a time, the overshoot is at most one call.
  - The frame check (`Sec-Fetch-Dest: iframe`) is no lock: browsers stop page scripts from setting it, but Fetch Metadata puts no limit on other clients, so `curl` can send it. `.claude/rules/security.md` already says so (not enforced).
  - The Portal's only rate limiting (`count_try`, login and reset) lives in `LocMemCache`, which Django documents as per process ("each process will have its own private cache instance"); the Portal runs `gunicorn --workers 1`, so this works today and resets on every restart (the existing `shortcut:` comment).
- **Settings reach the core** through the settings port (`voice/settings.py`, `load_settings`): the core asks the Portal for the ticket's Business. A demo Business is an ordinary Business row, so its name, instructions, languages and Theme reach the call page and the prompt with no new code.
- **Eval caps** (`tests/evals/caps.json`: 10 SEK per run, 30 per loop, 50 per day) cap paid eval runs only; nothing on the live path reads them.

## 2. Google's side: limits, prices and caps

- **Price** (`gemini-3.8-live`, paid tier, USD): input audio $3.00 per 1M tokens "or $0.005/min", output audio $12.00 per 1M "or $0.018/min", text in $0.75, text out $4.50 (output includes thinking). No cached-token rate is listed.
- **Cost grows with call length, faster than linearly.** The best-practices page: "As a session lengthens, the cost per turn increases because the conversational history is re-processed", and the accumulated audio is billed on every turn. `contextWindowCompression` is Google's way to stop "unbounded cost growth in long sessions". So the per-minute figures understate a long call.
- **Session limits:** audio-only sessions stop at 15 minutes without compression; a connection lasts about 10 minutes; resumption tokens hold for 2 hours. Our 600 s ceiling sits inside both.
- **Rate limits:** the rate-limit page gives no Live-specific concurrency numbers; hitting a spend-based limit returns `429 RESOURCE_EXHAUSTED`. What the call page shows on a 429 or 402 at call start: not checked.
- **Hard caps that exist:**
  - *Prepaid credit* (the project is on prepaid credit, DECISIONS.md 2026-10-18): when it runs out, "all API keys in all projects linked to that billing account will stop working simultaneously" with HTTP 402. A real hard stop, but it stops every Business's calls, not only the demo.
  - *Project spend cap* in AI Studio (monthly, per project): Google calls it "experimental and limited in scope"; billing data lags about 10 minutes, so it can overshoot. Keys have "no independent billing settings": every key in the project shares it, so it cannot single out the demo unless the demo runs on its own project.
  - *Billing account tier caps* ($250 a month at Tier 1): when reached, service pauses for all projects on the account until the 1st. Too coarse for the demo.
- **Cloud Billing budgets alert only:** "Setting an alerts-only budget doesn't automatically cap ... usage or spending." Thresholds default to 50, 90 and 100 per cent of actual spend, by email or Pub/Sub; cost data arrives hours late, and Google advises setting the budget "below your available funds". Good as a tripwire, not as the cap.

So the cap that holds has to be ours, checked before a ticket is minted; Google's tools are the backstop.

### What a demo call costs (estimate, to check against real Call records)

From the per-minute figures and the re-processing rule, with roughly 1,600 audio tokens per minute of conversation (from $0.005/min at $3/1M), a turn every 15 seconds, and a prompt of about 1,500 text tokens:

| Call | Turns | Input re-processed | Output audio | About |
|---|---|---|---|---|
| 3 minutes | 12 | ~29k audio + ~18k text tokens ≈ $0.10 | ~1.5 min ≈ $0.03 | **$0.13, ~1.4 SEK** |
| 10 minutes (today's ceiling) | 40 | ~320k audio + ~60k text tokens ≈ $1.00 | ~5 min ≈ $0.09 | **$1.10, ~12 SEK** |

SEK at about 11 per dollar, the rough figure the repo's other research uses (not a fetched rate). Today's short eval calls cost 0.06 to 0.15 SEK each (`docs/research/gemini-live-voice-and-language.md`), which fits the low end. The first ten real demo calls' `cost_usd` settle it.

## 3. The flow (MVP)

The smallest version reuses the Call button as it is: our landing page becomes one more website with the Call button on it.

1. **A demo Business.** Invited like any other (`invite_business`, Petter's own address), named for example "Example Salon", with the made-up facts the landing page already shows (`showcase()` in `portal/accounts/views.py`: hours, services, gift cards) typed into its settings page, Swedish and English, no Modules. Its saved website is the Portal's own domain, so the core lets only the landing page frame the call. Its `daily_budget_usd` is set to the demo budget (§ 4).
2. **The button.** `home()` renders the Call button tag (`call_button_tag(business)`, the same one the dashboard gives a Business) for the Business named by a new Portal setting, for example `DEMO_BUSINESS_ID`. Unset, or naming no Business, means no button: the default is off. The landing page's Content-Security-Policy must allow the script and the panel's frame (`portal_origin`, `core_origin`, as the dashboard preview does).
3. **The ticket.** The visitor presses the launcher; the panel opens `/call/<slug>/`; `call_link` checks the frame header and the saved website, then `to_core` checks the budget and mints a `call_link` ticket for the demo Business. New in the MVP: before minting, a per-address count for the demo Business (§ 4), and a daily call count (§ 4).
4. **The call.** The existing call page, in the demo Business's Theme, speaks the AI disclosure first (`DISCLOSURE` in `voice/agent.py`), runs up to the call ceiling, then ends. The Call record and Call log go to the Portal as for any call link call.

What the MVP changes in code: `home()` and its template (the tag), a Portal setting, the per-address and per-day counts in `call_link` (or `to_core`) for the demo Business, the landing page's CSP, tests at the Portal seam (`tests/portal/test_landing.py`, `tests/portal/test_call_link.py`). No core change, no contract change, no migration, no eval-required path, so no paid eval.

The other shape, a new call kind `demo` (its own `POST /demo-call/` from the landing page, a tab instead of a panel, `frame-ancestors 'none'` like a test call), buys a per-kind call ceiling in the core and demo calls apart from call link calls in `CALL_KINDS`. It costs a closed-set change on both sides (`voice/ticket.py` `KINDS`, `contract/call-record.schema.json`, `contract/call-log.schema.json`, `CALL_KINDS`, `BUDGET_COUNTED`, a migration for both kind constraints, the core's ceiling). Listed under § 8; the demo Business already keeps its calls apart on the totals page.

## 4. Spend caps, in layers (proposed numbers, Petter decides)

| Layer | Where | Proposed | Exists? | Visitor sees when it trips |
|---|---|---|---|---|
| One demo call at a time | core, `one_call` | 1 | yes | the page's "Call ended" state (wrong; a busy sentence is § 8) |
| Call ceiling | core, `MAX_CALL_SECS` | 600 s in the MVP (today's); 180 s once a `demo` kind exists | 600 s yes | the call ends; the ring is full |
| Calls per address per day | Portal, before the ticket | 3 | no | the refusal page in the panel |
| Calls per day, all visitors | Portal, before the ticket, counts the demo Business's Call records today | 40 | no | the refusal page |
| Daily budget | Portal, `to_core`, `daily_budget_usd` | $5 (~55 SEK) | yes | the refusal page |
| Kill switch | Portal setting `DEMO_BUSINESS_ID` unset (no button, no ticket); or the demo budget set to 0 | — | budget 0 yes | no button / the refusal page |
| Monthly alert | Cloud Billing budget on the project | e.g. 1,000 SEK a month, 50/90/100 % by email | not checked | nothing (Petter gets mail) |
| Hard backstop | prepaid credit (already) and the AI Studio project spend cap | Petter's figure | prepaid yes | every call fails (all Businesses) |

Why each:

- **The daily call count** is the cap that does not depend on pricing: § 1's fail-open (an unpriced first call counts as $0) leaves the budget blind if the price lookup is broken, while a count of records is not. At 40 calls of at most 10 minutes, the worst day is about 40 × $1.10 = $44 with pricing broken; at 3 minutes it would be about $5. With pricing working, the $5 budget trips first (roughly 35 three-minute calls).
- **The per-address count** stops one visitor emptying the day; it does not stop a crowd, which is what the daily count and budget are for. The address is the last `X-Forwarded-For` entry, as `client_address` already reads it (DECISIONS.md 2026-10-19, VOI-130). Kept in the cache like `count_try`, keyed on a SHA-256 of the address and the day, for 24 hours. Three, not one: an office or a mobile carrier puts many people behind one address.
- **One call at a time** also bounds the overshoot of the after-the-fact budget to one call, and caps the worst hour: at most about six 10-minute calls.
- **Worst month with the MVP numbers:** 30 × $5 plus one call's overshoot a day ≈ $180, ~2,000 SEK, if the button is busy every day. The monthly alert should sit below that.
- **The kill switch** needs no new command: unsetting `DEMO_BUSINESS_ID` on Dokploy and redeploying takes the button off (minutes). Setting the demo Business's budget to 0 works at once but needs a Django shell on the server today, since no command or page sets the budget; a `set_daily_budget` command under the prod-scripts contract is § 8.
- **Google's side** is the tripwire and the floor: a budget alert to Petter's mail, and the prepaid balance as the hard stop that already exists. A separate Google project and key for the demo would let a project spend cap single it out; that is a key and project change (Stop and ask).

## 5. Abuse and bots, without a new vendor

- **What already helps:** the call needs a microphone and a WebSocket held open, so a bot pays its own audio for every second of our spend; one call at a time means a bot can hold the demo but not multiply it; the daily count and budget turn any flood into "no demo today", not a bill.
- **Add in the MVP:** the per-address and daily counts (§ 4); a log line per mint and per refusal (Business id and the kind of refusal, never the address) so a flood shows in the server log.
- **Known holes, accepted for the MVP:**
  - A forged `Sec-Fetch-Dest` gets a ticket outside the panel (§ 1). Harmless beyond what the counts allow.
  - A ticket opens several calls within its 10 minutes, past the per-address count. One call at a time and the daily caps bound it; a single-use ticket, or a 60 s TTL for the demo, is § 8.
  - A bot that holds the one call slot all day blocks real visitors (no spend beyond the caps). The daily count and the 10-minute ceiling limit that to about 40 × 10 minutes.
  - Address rotation (IPv6, proxies) beats the per-address count; the daily caps still hold.
- **Agent misuse:** visitors will try to make the agent say odd things under our name. The prompt's rules apply as for any Business; nothing extra in the MVP. The ten eval Scenarios cover the disclosure and staying on the Business's facts, not a hostile visitor.
- **A CAPTCHA or bot-score service** (Turnstile, reCAPTCHA, hCaptcha) is a new vendor and a sub-processor of visitors' data: Petter's call, not in the MVP.

## 6. Privacy, legal and what is Stop and ask

- **Visitors are real people.** For the demo, Voice (Petter) is the controller: the demo Business is ours, not a customer's.
- **What is kept of a demo call today:** no audio and no transcript anywhere (the Live transcript goes only to the visitor's own page, `.claude/rules/security.md`); a Call record of numbers and times; a Call log of barge-in timings for 30 days (VOI-153); Google processes the audio as processor under the paid terms (DECISIONS.md 2026-10-18). The demo adds a hashed address in memory for 24 hours. GDPR recital 30 names internet protocol addresses as identifiers, so the counter is personal data too, kept short and hashed.
- **What the visitor must be told:** that it is an AI (the spoken disclosure, unchanged), and a notice beside the button or in the panel: what happens to the call (not recorded, timings kept 30 days, Google processes the audio) and a link to a privacy notice. A Voice privacy notice does not exist yet (`docs/research/call-log-legal-ground.md` § 8); the demo Business's `privacy_url` would point at it, so the call page shows the approved "Privacy notice" link.
- **Stop and ask, Petter decides each:**
  - Spend: the demo budget, the daily call count, the per-address count, the call ceiling, the monthly alert, and a separate Google project or key.
  - Caller-facing wording: the button's label and any notice beside it, the refusal sentence for a capped demo (reuse the approved one or a new one such as "The demo is taking a break. Try again tomorrow."), a "busy" sentence, and the privacy notice text.
  - Real people's data: the hashed address counter, and the privacy notice itself; a legal check before the button goes public.
  - A new vendor: a CAPTCHA, or anything else on the visitor's path.
  - A new Portal setting on Dokploy (`DEMO_BUSINESS_ID`) is a deploy setting.

## 7. How to measure it, without visitors' words

- **Already there, free:** the totals page (`/totals/`, operator only) shows each Business's calls, minutes and dollars per month, so the demo Business's row is the demo's numbers. Each Call record holds length and `cost_usd`; the Call logs page shows each call's barge-ins.
- **Add with the MVP:** a log line per ticket minted and per refusal, by kind (`per_address`, `per_day`, `budget`, `off`), so "button pressed" and "turned away" can be counted from the server log. Tickets minted minus Call records is roughly calls that never connected (microphone denied, page closed).
- **Read after a week:** calls per day, average and longest length, cost per call, share of calls that hit the ceiling, refusals by kind. Never the words, never the addresses.
- **Conversion** (a demo call followed by a "Request access" mail) is not measurable without tracking visitors: not in scope.

## 8. MVP and later

**MVP:** a demo Business with the landing page's made-up facts; the Call button on the landing page behind `DEMO_BUSINESS_ID`; per-address (3) and per-day (40) counts before the ticket; the $5 daily budget; the 600 s ceiling as today; a Cloud Billing alert; a notice and privacy link Petter words; mint and refusal log lines; Portal-seam tests.

**Later:**
- A `demo` call kind with its own 180 s ceiling in the core (cuts a worst-case call from ~$1.10 to ~$0.13).
- A "the demo is busy" state on the call page instead of "Call ended" when the slot is taken (caller wording).
- Single-use tickets (the core remembers a ticket's nonce until it expires), or a 60 s TTL for the demo.
- Fix the fail-open in `spent_today` for a Business with no priced call yet (count unpriced seconds at a stated ceiling rate), which also helps every customer.
- Per-address limits on every call link, not only the demo (a customer-facing change).
- A `set_daily_budget` management command (prod-scripts contract), so the kill switch works without a shell.
- Counts moved from the in-memory cache to Postgres before a second Portal worker.
- `contextWindowCompression` if demo calls run long.
- A separate Google project and key for the demo, with its own AI Studio spend cap.
- The example Module (opening hours) on the demo Business, so visitors hear an Action mid-call.
- A CAPTCHA vendor, if the counts are not enough.

## Open points

- What the call page shows when Google answers 402 (credit gone) or 429 at call start: not checked.
- Whether a Cloud Billing budget is set on the project today: not checked (no console access).
- The cost estimate in § 2 is arithmetic on Google's rates, not a measured demo call.
