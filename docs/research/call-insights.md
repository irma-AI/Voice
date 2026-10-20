# Call insights: what competitors offer, what Businesses value, what is legal without words

Researched 2026-10-19 for Petter. His question: "the more insights we can legally get from the calls the better, so we can provide more guidance to the business about their callers. Question is how we get that into the product in an agnostic way." His second instruction: build each idea as an MVP and iterate. This file is research only; no code changed, and it is not legal advice.

Legend: **[S]** read on the source page. **[E]** from a search-result excerpt of that page; the page itself was not opened. **[C]** a vendor's claim about its own product or market. **[I]** my inference. **[?]** not checked.

## Summary

- **Competitors' baseline**: a call log, a summary and a transcript for each call, often a recording, and a text or email when the call ends. All of them make the summary and transcript from stored words. Few go further. Telavox, RingCentral and Goodcall show the questions the agent could not answer. Jobber, ServiceTitan, RingCentral and Goodcall count outcome tags. Quo shows hour and weekday patterns. The voice-agent platforms (Retell, Vapi, ElevenLabs, Bland, Synthflow) all let the builder define post-call fields of fixed types: yes/no, number, a pick from a list, or text.
- **What Businesses value**: answering every call so no customer is lost has strong evidence, though the studies are mostly vendor-run. Caller details pushed fast by text or email is medium (reviews). A callback list is medium. Dashboards, trends, sentiment and "reasons for calling" rest on weak evidence: vendor pages only, no owner surveys. No Swedish survey on this was found.
- **Legal without words**: closed-list codes computed during or at the end of the call can be stored with no Caller's words or audio. Examples: how the call ended, which Actions ran, an outcome from a fixed list, a topic from a fixed list. Counts by hour and weekday can be stored the same way. They are still personal data tied to a call id, which is pseudonymous: the Business can often tell who called at 14:02. So they need the Business's instruction in the processing agreement and a line in its notice, but no new kind of risk. Summaries, transcripts and model-written "unanswered questions" are words. Each needs Petter's legal call first: a DPIA screening, Art. 9 content that turns up without warning, accuracy, and access requests.
- **Business-agnostic design**: every code comes from a fixed list Voice owns, or from the Business's own Actions. No industry fields. The database refuses a code outside the list, the way `CALL_KINDS` is enforced today.
- **First step**: show *when* callers call (hour and weekday) and *how calls ended* on the Recent calls page. It uses only data the core already has, needs no model call and stores no words. Callers turned away because the Business already had a call open become visible there too: today the core only writes them to its log (`voice/serve.py`, the `one_call.take` refusal).
- **Avoid**: sentiment from the voice. It would make Voice an emotion recognition system under the AI Act (Art. 3(39), recital 18), which is high-risk under Annex III from 2 Dec 2027 (Regulation (EU) 2026/1744).

## Sources

All read 2026-10-19. Vendor pages are claims about their own products **[C]**.

| # | Source | Link |
|---|---|---|
| 1 | Telavox, "AI capabilities" | https://www.telavox.com/ai-capabilities/ [S] |
| 2 | Telavox Support, "AI Receptionist" (404 when fetched) | https://support.telavox.com/en_US/administration/ai-receptionist [E] |
| 3 | Tell Sverige, "AI-receptionist för företag" | https://tellsverige.se/smart-partner/ai-receptionist [S] |
| 4 | Dstny, "Voice Agent" | https://dstny.se/en/products/ai-services/voice-agent [S] |
| 5 | Menodi, "AI-receptionist på svenska" | https://menodi.se/ai-receptionist [S] |
| 6 | Svaria, "AI Receptionist för företag" | https://svaria.io/ai-receptionist [S] |
| 7 | TechTell, "AI receptionist" | https://techtell.se/ai-receptionist [S] |
| 8 | BusinessWith, "Bästa AI Receptionist 2026" (comparison site, no date) | https://businesswith.se/ai-receptionist/ [S] |
| 9 | Rosie, home and pricing | https://heyrosie.com/ [S] |
| 10 | Goodcall, home and pricing | https://www.goodcall.com/ [S] |
| 11 | Smith.ai, "AI Receptionist" and pricing | https://www.smith.ai/ai-receptionist [S] |
| 12 | My AI Front Desk, home and pricing | https://www.myaifrontdesk.com/ [S] |
| 13 | Quo (formerly OpenPhone), "Sona" | https://www.quo.com/sona [S] |
| 14 | Quo, "Analytics" | https://www.quo.com/product/analytics [S] |
| 15 | RingCentral, "Intro to AI Receptionist analytics" (sign-in wall when fetched) and the GA press release, 30 June 2025 | https://support.ringcentral.com/article-v2/intro-to-ai-receptionist-analytics.html [E]; https://www.nasdaq.com/press-release/ringcentral-announces-general-availability-ai-receptionist-air-2025-06-30 [E] |
| 16 | Jobber Help Center, "Receptionist, powered by Jobber AI" | https://help.getjobber.com [E] |
| 17 | ServiceTitan Help, "Use the Voice Agent dashboard in Contact Center Pro" | https://help.servicetitan.com/docs/use-the-voice-agent-dashboard-in-contact-center-pro [E] |
| 18 | Dialpad Help, "AI Recap" | https://help.dialpad.com/docs/ai-recap [E] |
| 19 | Retell AI docs, "Post-call analysis" and "Data Storage Settings" | https://docs.retellai.com/features/post-call-analysis-overview [S]; https://docs.retellai.com/accounts/privacy-disable [E] |
| 20 | Vapi docs, "Call analysis" | https://docs.vapi.ai/assistants/call-analysis [S] |
| 21 | ElevenLabs docs, "Agent analysis", "Data collection", "Success evaluation", retention and Zero Retention Mode | https://elevenlabs.io/docs/agents-platform/customization/agent-analysis/data-collection [S]; retention pages [E] |
| 22 | Bland docs, "Analyze call" and citations | https://docs.bland.ai/api-v1/post/calls-id-analyze [S] |
| 23 | Synthflow docs, "Webhooks" | https://docs.synthflow.ai/webhooks [E] |
| 24 | PolyAI, "Data and insights" | https://poly.ai/data-and-insights [S] |
| 25 | Twilio docs, "Language Operators" | https://www.twilio.com/docs/conversational-intelligence/language-operators [S] |
| 26 | CallRail, "Conversation Intelligence", and Support articles on automation rules, AI features and retention | https://www.callrail.com/conversation-intelligence [S]; support.callrail.com [E] |
| 27 | CallTrackingMetrics, "Conversation analytics" | https://www.calltrackingmetrics.com/features/analytics-and-reporting/conversation-analytics [E] |
| 28 | Invoca, "Signal AI" | https://www.invoca.com/product/signal-ai [S] |
| 29 | WhatConverts, "AI Lead Analysis"; Marchex, "Call summaries" | whatconverts.com, marchex.com [E] |
| 30 | Quo blog, "Small business callback statistics" (16.7 million missed calls on Quo, published 20 Aug 2026) | https://www.quo.com/blog/small-business-callback-statistics/ [S][C] |
| 31 | JustCall blog, "Missed Call Statistics 2026" (compiles Invoca's 2026 benchmark and CallRail's 2025 consumer survey; flags untraceable figures), 16 Sep 2026 | https://justcall.io/blog/missed-call-statistics.html [S][C] |
| 32 | Moneypenny, "Small business call report", 21 Nov 2016 | https://moneypenny.com/us/resources/news/small-business-call-report/ [S][C] |
| 33 | Hiya blog, "Canadian businesses losing revenue due to unanswered calls", 5 Aug 2026 | https://blog.hiya.com/canadian-businesses-losing-revenue [S][C] |
| 34 | Trustpilot review pages for Smith.ai, Dialzara, My AI Front Desk and CallRail (small samples read) | https://www.trustpilot.com/review/smith.ai and siblings [S] |
| 35 | Ruby blog, "Who's calling your business after closing?" (undated) | https://www.ruby.com/blog/whos-calling-your-business-after-closing/ [S][C] |
| 36 | Spiris (Visma Spcs) newsroom, launch of its AI assistant | https://www.spiris.se/nyhetsrum/visma-spcs-lanserar-ai-assistent-for-hundratusentals-smaforetagare [S][C] |
| 37 | Nordea and Verian, "Bedrägerier mot småföretag 2025" | https://www.nordea.com/sv/doc/bedragerier-mot-smaforetag-2025-verian-nordea.pdf [S] |
| 38 | BlueLink ERP blog, "Are business software dashboards invisible?" (undated, no survey) | https://www.bluelinkerp.com/blog/are-business-software-dashboards-invisible/ [S] |
| 39 | Regulation (EU) 2024/1689 (AI Act), Art. 3(39), 5(1)(f), 50, Annex III point 1(c), recital 18, via artificialintelligenceact.eu | https://artificialintelligenceact.eu/article/50/, https://artificialintelligenceact.eu/recital/18/ [S] |
| 40 | Regulation (EU) 2026/1744 (Digital Omnibus on AI), 8 July 2026, OJ 24 July 2026 | https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=OJ:L_202601744 [S] |
| 41 | GDPR, Regulation (EU) 2016/679: Art. 4(1), 5, 6, 9, 13, 25, 28, 35, recitals 26 and 35 (articles as already read for `docs/research/call-log-legal-ground.md`; not re-fetched) | https://eur-lex.europa.eu/eli/reg/2016/679/oj [?] |
| 42 | Datainspektionen, list of processing that needs a DPIA under Art. 35(4), 17 Jan 2019 (only its metadata was readable) | https://www.imy.se/link/61a6f670db5040bba1dcf34bed6fe4c6.aspx [E] |
| 43 | Art. 29 Working Party, Opinion 05/2014 on anonymisation techniques (WP216) (not re-read) | [?] |
| 44 | CNIL, "L'écoute et l'enregistrement des appels sur le lieu de travail", 2009 (the page says it is out of date) | https://www.cnil.fr/fr/lecoute-et-lenregistrement-des-appels-sur-le-lieu-de-travail [S] |
| 45 | Datainspektionen, decision on TeliaSonera's recording of customer-service calls, 12 May 2016 | https://www.imy.se/globalassets/dokument/beslut/2016-05-12-telia.pdf [E] |

Not reached or found: G2 and Capterra (403), Reddit, Weblink and Freshcom (no AI receptionist found), a Telia Smart Connect AI receptionist (none found), Gartner and Opus Research (paywalled), the CJEU judgment C-413/23 P on pseudonymised data (read only through a law firm's commentary).

## 1. What competitors offer

### Swedish and Nordic

| Product | Insights | How shown | What it stores |
|---|---|---|---|
| Telavox AI Receptionist and AI Assist [1][2] | Call volume, how each call was handled, what was booked, most common topics; a recurring email of questions the receptionist could not answer, "to update the FAQ" [E] | Dashboard in the Telavox app (analytics in beta); email | Full transcripts; transcription via Whisper/OpenAI, "data will be sent to the US" [E]. Sold as a premium upgrade, no public price |
| Tell Sverige (resells the Telavox receptionist) [3] | Calls received (including today), top topics such as bookings, "what customers actually ask" | Dashboard | Transcripts |
| Dstny Voice Agent [4] | Transcript and summary of every call; escalations become tickets | Email or CRM | Transcripts and summaries; analytics and recording are a separate product |
| Menodi [5] | A summary per call (what was resolved, what needs follow-up), customer history, messages | App | Summaries; EU storage. From 795 kr/month |
| Svaria [6] | Summary, caller number, transcript and Actions taken, sent as the call ends | Telegram, SMS or email | Transcripts and recordings, EU processing [C] |
| TechTell [7] | A transcript for every call; a summary right after; search by number or by what was said | Dashboard | Transcripts, recordings implied; from 999 kr/month, 24–36 month binding |

The Swedish startups stop at a summary plus a notification. Only the Telavox family has a dashboard with topics and unanswered questions [I]. A Swedish comparison site lists "statistics on calls, common questions and response times" as a feature category without naming a vendor [8].

### International AI receptionists for small businesses

| Product | Insights | How shown | What it stores |
|---|---|---|---|
| Rosie [9] | Summary, transcript and recording of every call; message taking; spam detection | Email, text or app alert when each call ends | Recordings and transcripts, all plans (from $49/month) |
| Goodcall [10] | Custom weekly metrics (booked, new leads, handed to you); "Action chips" tagging what happened; when it cannot answer it "tells you what it heard" | Dashboard; leads by text and email at call end | "Every call recorded and transcribed"; history kept 30 days, 90 days or forever, by tier |
| Smith.ai AI Receptionist [11] | Summaries, call volume, appointments, a quality score, "self-healing FAQs" that surface knowledge gaps | Dashboard; summaries routed to staff | Recording and transcription on every plan, including free |
| My AI Front Desk [12] | "Intent, timing, sentiment, and any field you define in plain English" [C] | Dashboards | Last 200 interaction logs on the $79 plan |
| Quo Sona [13][14] | Summary and transcript per call; caller's name, reason and urgency. Analytics: missed, voicemail, forwarded and abandoned as separate outcomes; volume over time against the previous period; hour and weekday breakdown; trends of AI call tags; CSV export | Call list and analytics on every device | Recording of every Sona call |
| RingCentral AI Receptionist [15] | Resolved and unresolved calls, what resolved them (knowledge base, hours, FAQ), transfers, the top unresolved questions with counts [E] | Analytics dashboard and a per-call history | Call summaries on transfers [E] |
| Jobber Receptionist [16] | Action tags per conversation (general inquiry, request created, job scheduled, took a message, spam, escalated); outcome and time-saved cards [E] | Conversation log and dashboard | Recording and transcript per conversation [E] |
| ServiceTitan Voice Agent [17] | Booking rate, revenue from booked jobs, outcomes (booked, rescheduled, lead collected), escalation reasons, sentiment [E] | Dashboard | Transcripts [E] |
| Dialpad AI Recap [18] | Summary, AI outcome, AI call purpose, action items, sentiment [E] | Per-call recap | Transcript [E] |

### Voice-agent platforms (builders of agents like ours)

Each one runs a model over the transcript after the call and returns fields the builder defines:

- **Retell AI** [19]: built-in fields are a summary, sentiment (read from the transcript text), "call successful" and voicemail. Custom fields are Text, Selector (a pick from a fixed list), Boolean or Number, "evaluated by an LLM" after the call [S]. A storage setting, `basic_attributes_only`, keeps the fields without the transcript or recording [E].
- **Vapi** [20]: a summary (2–3 sentences by default), structured data from a JSON Schema, and a success evaluation (pass/fail, numeric scale, checklist and others). The input is "a transcript of a call" [S].
- **ElevenLabs Agents** [21]: evaluation criteria return success, failure or unknown. Data collection fields are string, boolean, integer or number, run over the transcript [S]. Zero Retention Mode stores no transcripts and sends results by webhook only [E].
- **Bland** [22]: the analyze endpoint takes questions with types and returns answers, or null where the call holds none [S]. Synthflow [23] returns collected variables and true, false, partial or not applicable [E].
- **PolyAI** [24]: dashboards of containment, booking type and cancellation reasons, plus a chat interface over past conversations [S].
- **Twilio** [25]: Language Operators classify transcripts into predefined categories, extract entities, or generate text or JSON [S].

### Call tracking and analytics

- **CallRail** [26]: transcripts, key-term spotting and automation rules that tag or score a call. AI summaries, sentiment, lead scoring and "conversion signals" (booked appointment) are a premium add-on. Records and recordings are kept 25 months; transcription needs recording [E].
- **CallTrackingMetrics** [27]: prompts over transcripts, star scores that trigger alerts [E]. **Invoca** [28]: true/false outcome signals from models trained on a business's calls [S]. **WhatConverts** and **Marchex** [29]: summaries, intent, topics and alerts on missed opportunities [E].

### What this means for Voice [I]

- Every competitor that shows reasons, topics or unanswered questions makes them from stored transcripts. None makes them without one.
- The platforms do show the shape Voice can copy without words. Their outputs are fixed-type fields (Selector, Boolean, pass/fail), and Retell and ElevenLabs offer a mode that keeps the fields and drops the transcript. Voice can go one step further and never have the transcript stored in the first place.
- The insights that need no words at all are volume, time of day, how a call ended and which Actions ran. Quo sells exactly these.

## 2. What small businesses value, ranked

Independent evidence is thin. Missed calls have numbers, mostly from vendors. Everything else rests on small samples of reviews, or on vendor pages only.

1. **Every call answered, no customer lost (strong, mostly vendor data).**
   - Invoca's 2026 benchmark over its own customers' calls: 44% of inbound calls never reach a person [31][C].
   - Of 16.7 million missed calls on Quo, 69% got no callback within 48 hours [30][C].
   - In 2016, 69% of callers who reached voicemail hung up without a message [32][C].
   - 87% of Canadian business respondents lost deals over phone reachability [33][C].
   - On Trustpilot, catching calls and leads is the top praise for Smith.ai, Dialzara and My AI Front Desk [34].
   - For Voice the call is a web call, so the nearest thing to a missed call is a Caller turned away: the Business was already on a call, its daily budget was spent, or the call failed [I].
2. **Caller details pushed at once, by text or email (medium; reviews only).** About 7 of roughly 24 visible Smith.ai reviews praise the summary or message content, and 2 the email or text delivery. A Dialzara reviewer credits the text and email transcript with not missing calls [34]. Dashboards are almost never mentioned, and once negatively (CallRail) [34]. One undated vendor blog says owners stop looking at dashboards, without a survey behind it [38].
3. **A callback list with qualified leads, and speed (medium).** Reviews praise intake and qualifying questions [34]. Studies compiled by JustCall show response odds drop as callbacks slow [31][C].
4. **Spam and fraud filtered (medium).** Repeated in reviews [34]. In Sweden, 43% of 701 small firms faced a fraud attempt, and 61% of those attempts came by phone or SMS [37].
5. **Accurate messages (medium, as a complaint).** Reviewers notice wrong summaries [34], so a summary is only worth what it gets right [I].
6. **Recordings and transcripts for disputes (medium for call-tracking buyers, weak for micro-businesses)** [26][34].
7. **When people call: after hours and peak times (weak to medium).** Ruby reports after-hours calls grew 18% from 2020 to 2021 [35][C]. Visma Spcs says just over 40% of the questions to its AI assistant came outside working hours [36][C]. No owner was found asking for a heatmap.
8. **Marketing attribution** matters to CallRail's agency buyers, not to owner-run shops (no evidence either way).
9. **Reasons for calling, unanswered questions, sentiment, trends (weak).** Vendor pages only; no owner survey or review asks for them. They are still the competitors' differentiators, so the demand may be latent rather than absent [I].

## 3. Legal: what needs words and what does not

Builds on `docs/research/call-log-legal-ground.md` (VOI-155) and `docs/privacy/README.md`. This section is research, not legal advice.

### Personal data even without words

- A code stored against a call id is "information relating to" the person who called. The test is whether that person is identifiable by means "reasonably likely to be used" (GDPR Art. 4(1), recital 26) [41]. The Business can often link a call at 14:02 to the person it then booked or called back. So per-call codes are pseudonymous personal data for both the Business and Voice. The web Channel carries no phone number, which makes them less identifying but not anonymous [I].
- Counts per hour, weekday or code, with no call id, can be anonymous [43]. A count of one in a small cell can still be linked to a person. Petter's legal call is whether the Portal must hide small counts. For the Business's own view it matters less: the Business is the controller and already knows its callers [I].

### Special-category data (Art. 9) in a code

- "Health" includes information collected when someone registers for health care (Art. 9(1), 4(15), recital 35) [41].
- A topic code such as "booking" at a psychotherapy practice can reveal health data through the Business's identity alone. The CJEU reads Art. 9 broadly enough to cover data that reveals a category indirectly (C-184/20, C-21/23; cited from knowledge [?]).
- A generic list (hours, prices, booking, location, complaint, other) does not name a condition. It still sits on a call to a clinic [I].
- Flag for Petter: whether per-call topic codes are acceptable for health-care Businesses at all, or must be counts only.

### Roles, ground, notice, retention

- **Roles.** The Business decides why insights are made, so it is the controller and Voice its processor. The processing agreement (Art. 28(3)(a)) must list insights as a documented instruction, with the data categories and retention [41]. That agreement does not exist yet (`docs/privacy/README.md` § 6).
- **Voice becomes a controller if it uses the codes for its own purposes**, such as comparing Businesses, tuning the prompt or product analytics (Art. 28(10)). Only truly anonymous aggregates are safe for that [41][43].
- **Ground.** Art. 6(1)(b) covers what the Caller asked for. Insights for the Business's own planning fit 6(1)(f), legitimate interest: codes and counts balance far better than words. The Business carries the three-step assessment, and Callers may object (Art. 21) [41].
- **Notice.** Art. 13 information "at the time" [41]. A layered notice works: a short line at call start, with the full text behind a link [44]. The call page already links the Business's own privacy notice (`Business.privacy_url`), and that notice would name insights. Any wording Voice adds to the call page is caller-facing: Petter's call.
- **Purpose limitation.** Insights are a purpose beside answering the call (Art. 5(1)(b)). Adding them later means the Art. 6(4) compatibility test and an updated notice before they start (Art. 13(3)) [41].
- **Retention.** A fixed period per data set (Art. 5(1)(e)). Codes on the Call record are kept with it for billing today, so a code that outlives the Business's purpose needs either a period of its own or a home in the Call log, which is deleted after 30 days [I].
- **Minimisation.** Closed lists over free text, computed during the call, keeping no audio or text, is Art. 25's data protection by design in practice [41].
- **Precedent on purpose and information.** Datainspektionen found TeliaSonera lacked a legal basis for recording customer-service calls to coach staff, and told callers too little [45]. The purpose, and telling the caller, are what a regulator tests [I].

### What needs words, and what that adds

| Insight | Needs words? | Extra conditions |
|---|---|---|
| Calls per hour and weekday, length, kind | No: the Call record already holds them | None beyond today |
| How the call ended (Caller hung up, agent ended, time limit, Business busy, budget spent, error) | No: the core knows it | The Call record's field list grows, so `.claude/rules/security.md` comes first |
| Which Actions ran, and whether they succeeded | No: Action names come from the Business's own Modules | Same; never arguments or answers |
| Outcome and topic from a fixed list, chosen during the call | No words stored; the model reads the words live, as it already does | Processing agreement instruction; the Business's notice; Art. 9 question for clinics |
| "The agent could not answer" as a code with a topic | No | Same as above |
| An unanswered question in the model's words | Yes: a sentence derived from the Caller's words | Petter's legal call: third-party and Art. 9 content turns up without warning; accuracy (Art. 5(1)(d)); access and erasure requests; DPIA screening |
| Per-call summary | Yes | As above, plus storing it is a new store of words about real Callers |
| Transcript or recording | Yes | As above; Brottsbalken 4 kap. 9 a § and the open questions in `call-log-legal-ground.md` § 6 |
| Sentiment from tone of voice | Inferred from audio | AI Act emotion recognition (below) |

### DPIA

IMY's Art. 35(4) list requires a DPIA when two of its criteria hold, among them sensitive data and innovative technology [42][E]. A per-call free-text store for clinics would plausibly hit both. Codes and counts call for a written screening. The DPIA is the Business's duty, and Voice as processor must help (Art. 28(3)(f)) [41][I].

### EU AI Act

- **Disclosure.** Art. 50(1) applies from 2 Aug 2026: people must be told they are talking to an AI system. Voice already says so (`DISCLOSURE`) [39]. The Digital Omnibus changed only Art. 50(7) in that article [40].
- **Emotion recognition.** An emotion recognition system infers emotions or intentions "on the basis of their biometric data". Physical states such as pain or fatigue, and "the mere detection of readily apparent expressions", are excluded (Art. 3(39), recital 18) [39].
  - Sentiment read from transcript text is not biometric [I]. Frustration read from pitch or tone plausibly is.
  - Art. 5(1)(f) bans emotion recognition only in workplaces and education [39]. Annex III point 1(c) makes it high-risk, and Regulation (EU) 2026/1744 sets Annex III duties from 2 Dec 2027 [39][40].
  - Voice's barge-in levels are not emotion inference, as long as they are never turned into a mood [I].
- **Synthetic audio marking.** Whether the agent's synthetic voice falls under Art. 50(2) is a separate open question. It is not an insight [?].

### Flags for Petter's legal call

1. Topic codes per call for health-care Businesses: allowed, counts only, or not at all.
2. Whether any model-written words about real Callers (an unanswered question, a summary) may be stored.
3. Whether the Portal must hide small counts.
4. The processing agreement's insights clause, and a template line for the Business's notice.

## 4. A business-agnostic design

### What lands where

1. **Already stored**: start time, length and kind on the Call record. The hour and weekday counts are a query over the Business's own rows. No change to the core.
2. **One new closed-set code on the Call record: how the call ended.** The core already knows most of it:
   - Pipecat's `EndFrame` or `CancelFrame` (the barge-in `end` event's `reason`);
   - the session timeout (`MAX_CALL_SECS`);
   - the busy refusal in `voice/serve.py`, which would also send a record for the turned-away call. A spent budget is refused earlier, in the Portal (`to_core` in `portal/accounts/views.py`), which can count it itself.

   The database refuses a code outside the list, as `CALL_KINDS` is refused today (`portal/accounts/models.py`). A test that enumerates the set keeps every page handling each code (Hard rule 4). Recording a refused call changes the Call record's definition ("one call that reached the model"), so `GLOSSARY.md` needs updating. The alternative is a separate count of refused calls [I].
3. **Action names used** in the call, as a list of codes. They are the Business's own Modules' tool names, which makes them agnostic by construction. The core sees each tool call (the eval `CallRecorder` already writes `tool_call` with the name only).
4. **Later, outcome and topic from Voice's fixed lists:**
   - outcome: answered, took a message or handed off, could not answer, not a real call;
   - topic: hours, prices, booking, location, order or delivery, complaint, other.

   No industry list and no Business-defined list. "Other" with a "could not answer" outcome is the signal for "add this to your Instructions" [I].

### Where the tags are computed

| Option | Cost | Words leave the call? | Fits the rules? |
|---|---|---|---|
| A. The core, from what it already knows (end code, Actions) | None | No | Yes; no prompt change, no eval receipt |
| B. The live model calls a core-provided function (`note_call(outcome, topic)` with enum parameters) before the goodbye | No extra model call; a prompt change, so a paid `make eval` | No: Gemini's function arguments are constrained to the enum [?] | ADR 0001: "the core takes no actions". Recording a code is bookkeeping, not an Action toward the world, but it would be the first tool the core itself offers. Petter's call, possibly an ADR note |
| C. A second, text-only model call at call end over the in-memory transcript | A small spend per call (Stop and ask); the words go to Google a second time, under the same terms | To Google only, not stored | Adds a model call per call; most accurate tags; same store rules as B |

The MVP is A. B is the cheapest way to topics later. C only if B's accuracy fails in evals.

### Store rules (Hard rule 1)

- New Call record columns hold codes only. A CHECK constraint lists each set, and there is no text column. A list of Action names gets the same rule as Module names: short, no spaces.
- The contract (`contract/call-record.schema.json`) and the security rule's field list name each field first. The parity test that already holds the record, the contract and the field list together covers the new fields.

### Tests (the seams in `CLAUDE.md` § Tests)

- **Portal seam** (`make test-db`): the database refuses an unknown end code and an Action name with a space; the Recent calls page shows each end code by name, through a test that enumerates the set; the hour and weekday counts read only the logged-in Business's rows.
- **Checks** (`make test`): a stored synthetic call record that carries an end code passes its contract check, and a record with free text in it fails.
- **Eval channel** (paid, Petter's go): only for option B. Each Scenario states the outcome and topic it expects; a check compares them. A tagging-accuracy check is a change to the eval checks, so it gets a second read and `evals-approved`.

### How a Business sees it (MVP first)

1. Recent calls page: one row of counts per weekday and hour band, calls this week against last week, and how each call ended.
2. Later: a weekly email of the same counts. Push is what reviewers praise (§ 2), and the Portal already sends mail. That makes it a scheduled job, which needs its own "seen firing" check.
3. Later: the agent endpoint (VOI-112) serves the same counts to the Business's own agent, through the same one way in.

## 5. Recommendations, ranked

| # | What | Impact for the Business | Effort | Legal risk |
|---|---|---|---|---|
| 1 | **When callers call**: hour and weekday counts and this week against last, on Recent calls, from existing Call records | Medium: staffing, opening hours, proof the agent picks up | Small: one Portal query and page | None new |
| 2 | **How calls ended, and turned-away callers**: one closed-set end code on the Call record, including calls refused because the Business was busy or its budget was spent | High: the "missed call" Businesses care most about (§ 2.1), made visible | Small to medium: core, contract, migration, page | Low: a code, no words |
| 3 | **Which Actions ran**: Action names per call, shown as counts ("booking: 14 this week") | Medium to high: an outcome measure that is agnostic by construction | Small to medium: core and record | Low: names from the Business's own Modules, never arguments |
| 4 | **Outcome and topic from fixed lists, tagged by the live model** (option B) | High: "could not answer" by topic, the differentiator of Telavox and RingCentral | Medium: a core function, a prompt change, a paid eval, a Scenario check | Medium: Art. 9 for clinics, the processing agreement, the Business's notice |
| 5 | **Unanswered questions in words** | Highest: tells the Business what to add to its Instructions | Medium | High: needs Petter's legal call and a DPIA screening first; Later |
| — | Not recommended: sentiment from the voice (AI Act), and recordings or transcripts of real Callers (out of scope by VOI-152) | | | |

Recommended first step: #1. It is a Portal-only change, using data already stored. #2 and #3 follow, each a small core change with no model call, and VOI-188's outcome measures can reuse them.

## Not checked

- Gemini Live's enforcement of enum arguments in function calls (option B) [?].
- The GDPR articles were not re-fetched for this file (see `call-log-legal-ground.md` for the read text).
- IMY's DPIA list content, the CJEU judgments cited from knowledge, and EDPB paragraph numbers.
- RingCentral's analytics page (behind sign-in), and the Jobber and ServiceTitan help pages (search excerpts only).
- Vendor prices change often; the ones above are as shown on 2026-10-19.
