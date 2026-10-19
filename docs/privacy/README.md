# Privacy: who processes what, and under which terms

What a Business, and the enterprise customer's data protection officer, needs to know about a Voice call: who handles the data, what each party gets, how long it is kept, on which lawful basis, and who is the controller. Written 2026-10-18 from `docs/research/gemini-api-data-terms.md` (Google's terms, read 2026-10-18) and the code at that date; the research file carries the sources. Where this page says "proposed" or "not checked", nothing enforces it yet (`CLAUDE.md` § Hard rules 7).

Terms as in `GLOSSARY.md`: a **Business** runs its agent through Voice; a **Caller** talks to it; the **Portal** is where the Business logs in; the **core** runs the call.

## 1. Controller and processor

- **The Business is the controller toward its Callers.** It decides that an AI agent answers its calls, what the agent knows (its facts) and what it is for. It owes its Callers the information in GDPR Articles 13 and 14 and must tell them before they speak with the agent.
- **Voice (the operator who runs the hosted Portal and core) is the Business's processor** (Article 28): it runs the call on the Business's instructions and keeps nothing of the conversation (§ 3). A written processing agreement between Voice and each Business does not exist yet: it is needed before the first paying customer (open point, § 6).
- **Google is Voice's sub-processor** for the model (§ 2). The other parties in § 2 process no Caller data.
- **Toward the Business's own staff** (the Account's email and the Business's name, facts, logo, website domain and privacy notice address), Voice is the controller: that data is what running the Portal needs.
- **A kept copy of a test call's words and audio** (planned in VOI-160, not built): Voice is the controller, because the purpose (finding faults in Voice) is Voice's own; a processor that sets its own purpose is a controller anyway (Article 28(10)). `docs/research/call-log-legal-ground.md` § 2.

What Voice gives the Business for its notice: the call page shows the AI disclosure ("You are talking to an AI assistant.") before and during every call, and links the Business's own privacy notice beside it when the Business has saved its address in the Portal's settings (`Business.privacy_url`, https only; the database refuses anything else). The text of the notice is the Business's: Voice stores an address, never the words.

## 2. Sub-processors and other parties

| Party | Role | What it gets | Terms | Where |
|---|---|---|---|---|
| Google (Gemini API through AI Studio, `generativelanguage.googleapis.com`) | Model: sub-processor for the call | The Caller's voice (audio, live), the Business's name and facts in the system instruction, the agent's spoken replies, the names and answers of any Module the agent used | Gemini API Additional Terms, Paid Services (the project has an active Cloud Billing account: § 5); the Data Processing Addendum for Products Where Google is a Data Processor (business.safety.google/processorterms, v10, 2026-05-07), which lists "Gemini API Paid Services". No training on prompts or replies. Prompts, context and outputs are kept 55 days for abuse monitoring, readable by authorised Google staff, with no opt-out | No commitment: "any country in which Google or its agents maintain facilities". Transfers under the DPA's Appendix 3 (EU standard contractual clauses). An EU region needs the move to Vertex AI (VOI-139) |
| HostUp (hostup.se) | Hosting of the Portal, the core and their Postgres (Dokploy on a HostUp server), the Portal's outgoing mail, DNS | Everything stored (§ 3) and the servers' logs; the invite and reset emails to a Business's staff | HostUp's terms (not read here) | Server location: not checked |
| GitHub | Source code, CI, the public repository | Code and test fixtures with synthetic people only (`.claude/rules/security.md`); no Caller or Business data | GitHub's terms | |
| Linear | Tickets | What Petter and the agents write in tickets: no Caller data; a Business may be named when a ticket concerns it | Linear's terms | |
| Anthropic | Coding agents (Claude Code) that read tickets, code, CI output and, when asked, the apps' logs on Dokploy (`docs/agents/agent-access.md`) | Whatever those hold: call ids, token counts, timings; never audio or transcripts, which are never stored or logged (§ 3) | Anthropic's commercial terms | |

Not a party: Callers' audio never goes to the Portal, to Linear or to GitHub; the Live transcript goes only to the Caller's own page.

## 3. Data items, where they live, how long

| Data | Personal data? | Held by Voice | Retention | Also at |
|---|---|---|---|---|
| Caller audio, both directions | Yes (voice, and whatever the Caller says) | Not stored: streamed from the Caller's browser through the core to Google and back | Nothing to keep | Google, 55 days (abuse monitoring) |
| Live transcript (Gemini's transcription, shown on the call page) | Yes | Not stored, not logged (`tests/test_serve.py` fails if it reaches a log) | Nothing to keep | Google, within the 55 days above |
| Call record (call id, Business, kind, start time, length, token counts, cost) | No person in it; it says a Business had a call at a time | Portal's Postgres, written once, never changed or deleted by the application (database trigger) | Kept for billing after offboarding, keyed by the Business's number, whose name and account are emptied (§ 3a) | Container logs (same numbers, § below) |
| Call log: the barge-in log of one call (timings, levels, scores, event names, call id; VOI-153, VOI-154) | No | Portal's Postgres, written once and never changed (database trigger); the database refuses a field `.claude/rules/security.md` does not list, and any value with a space in it | 30 days from the call's start: the database refuses deleting it before then. Nothing deletes it after yet (VOI-157), so until then it stays longer | Container logs (the same lines, § below); a text file the operator downloads from the Call log page (`/logs/`, VOI-158) to hand to a coding agent |
| Container logs of the core and the Portal (the lines in `.claude/rules/security.md`; the web server's access log may hold the Caller's IP address: not checked) | IP addresses, if present | Dokploy on the HostUp server | Proposed: 30 days (not checked, as above) | Anthropic, when an agent reads them |
| Postgres backups | Same as the Portal's database | Handled outside the repository | Proposed: 30 days (not checked) | |
| Business account: email, name, facts, languages, logo, accent, website domain, privacy notice address | Yes (email, and anything personal the Business writes in its facts) | Portal's Postgres | While the Business is a customer, then emptied by offboarding (§ 3a); the facts also go to Google with every call | Google (facts), HostUp (mail to the email) |
| Access tokens | No (a SHA-256 hash, a label, times; offboarding blanks the label) | Portal's Postgres | Until revoked; a revoked token stays as a row | |
| Eval runs (`make eval`) | No: stored Caller audio is synthetic | Petter's PC, or the GitHub Actions run's logs | Local; the eval Business is fictional | Google, 55 days |

Nothing in this table is a cache or queue: Postgres is the only store (`.claude/rules/data.md`).

## 3a. Deleting a Business's data (offboarding)

The one offboarding path is the `offboard_business <email>` command (nothing else is stopped from editing the same columns: not enforced) (`.claude/rules/prod-scripts.md`: a dry run first, then `--execute` with the reviewed plan's hash and `--target`). In one transaction it revokes every Access token and blanks each one's label (to `Token <its number>`: a label may name a person), deletes the Modules, empties the Business's name (to `Business <its number>`), facts, website domain, logo, accent and privacy notice address, sets its call link's daily budget to $0, and closes the Account: a tombstone email (`deleted-<the Account's number>@invalid`), no usable password, no last login time, inactive. The plan the operator reviews shows the Business's current name and website domain. The Business row and its Call records stay, keyed by number, for billing; its Call logs stay until their 30 days run out (§ 3). The audit log names ids and the operator's OS user only. `tests/portal/test_offboard.py` reads every column afterwards. Not covered: copies already in Postgres backups and container logs until their retention runs out (§ 3, not checked), Google's 55-day copy of facts sent with past calls, the logo in Callers' browsers, which may keep it for up to a year (`Cache-Control: public, immutable`), and a Portal request already running when the command commits: a settings save or a new token from it can write data back or escape revocation with its label (no row lock; run the command again to be sure).

## 4. Lawful basis, per data item (proposed; Petter confirms)

The Business, as controller, chooses its basis; these are the ones its notice would normally name. Voice as processor needs none of its own for the Caller's data: it acts on the Business's instructions.

| Data | Controller | Basis the controller would name |
|---|---|---|
| Caller audio and transcript during the call | The Business | Article 6(1)(f), legitimate interest in answering the calls it receives, or 6(1)(b) where the Caller asks for the Business's service. The Caller is told before speaking (the disclosure and the Business's notice). Nothing is recorded by Voice |
| The 55-day abuse-monitoring copy at Google | The Business, through Voice and Google's processor terms | The same basis; the transfer rests on Google's DPA Appendix 3 (standard contractual clauses). Shortening it is not possible on this API (VOI-139 moves the model to a chosen EU region) |
| Call records and container logs (call ids, counts, timings, possibly IP addresses) | Voice | Article 6(1)(f): billing the Business, keeping the service running and secure |
| Business account data (email, name, facts) | Voice | Article 6(1)(b): the agreement with the Business; the email is how its staff log in and reset passwords |
| Test call words and audio, kept 30 days (VOI-160, not built) | Voice | Article 6(1)(f): finding and fixing faults in the service, with a written assessment before the first kept call, a notice on the test call page before the call, and a way to object (`docs/research/call-log-legal-ground.md` § 4, § 5). Consent fits poorly: it would be bundled with the button |
| Facts the Business writes that name people (a staff member's name and hours, say) | The Business | Its own basis toward those people; Voice sends the facts to Google with every call, so the Business should write only what the agent may say aloud |

## 5. Google tier

Google's data terms depend on whether the Cloud project behind the key has an active Cloud Billing account (Paid Services), not on the key or the model. Voice's project is on the paid tier: Petter confirmed on 2026-10-18 that the Google Cloud billing account behind the key holds his prepaid credit (`DECISIONS.md`, `RESOLVED` 2026-10-18). An account in the EEA gets the paid data terms on free quota too, with the 55-day abuse log in both cases. The move to Vertex AI (Google Cloud Terms, Cloud Data Processing Addendum, Google Cloud subprocessor list, a chosen EU region) is VOI-139 and waits for Petter: a vendor and billing change.

## 6. Open points

- A processing agreement (Article 28) between Voice and each Business, and a template notice a Business may start from: before the first paying customer.
- Retention: none of the proposed periods in § 3 is enforced; log retention on Dokploy and the backup policy each need a ticket and a `DECISIONS.md` line once set.
- HostUp's server location and terms: not read.
- Keeping test call words and audio (`docs/research/call-log-legal-ground.md` § 8): no Voice privacy notice exists for the test call notice to link to, the legal person behind Voice is not named, the legitimate interest assessment is not written, and whether a DPIA is needed is not checked. The notice wording waits for Petter (`DECISIONS.md`, ESCALATED 2026-10-19); it also needs a legal check.
- Whether Google publishes a sub-processor list for "Gemini API Paid Services": not found on 2026-10-18 (`docs/research/gemini-api-data-terms.md` § 3).
