# Four-surface redesign: the grilled brief

Written 2026-10-17 from a grilling session with Petter (`/next-step` → Feature flow → `grill-with-docs`). It holds what each surface must do and what Petter decided. The look is not decided here: it comes next from `/impeccable` new-work (§1–5, decision page) and lands in `DESIGN.md`. Then `to-spec` and `to-tickets` work from this file.

Context it builds on: `PRODUCT.md`, `CONTEXT.md` (Theme and Live transcript were added in this session), ADR 0001 and 0002, the embedded Call button spec VOI-69 and `docs/research/embedded-call-button.md`.

## The ask

Petter, verbatim: "The current design is just placeholder for testing but i want to design both a landing page outside the portal, then the portal itself, and finally the call page and the call button. all those four parts needs to be considered and have matching styles."

## Across all four surfaces

- One shared visual world, decided once and recorded in `DESIGN.md`. Every surface uses it.
- A Business's **Theme** (logo and one accent colour) shows only to its Callers: on the call page and the Call button. The landing page and the Portal keep Voice's own look.
- All UI text is English for now, because the code is open source and language-agnostic. Translations, Swedish first, cover the Portal, the landing page and the call page (VOI-67). VOI-76 researches the framework first, and VOI-67 is blocked by it.
- WCAG 2.2 AA for every surface (`PRODUCT.md`).

## 1. Landing page

- **Where:** the Portal's logged-out `/`, on the Portal's own Django app and host. No new app or deploy.
- **Language:** English.
- **Job (Petter's answer):** "Showcase the functionality + email + login + self host + sell the hosted service (and showcase all the versatile use cases (implemented or not))".
  - **Show the functionality:** a scripted, animated example call, clearly labelled as an example, built like the real call page (who is speaking plus Live transcript). No model, no cost per visit.
  - **Use cases, built or not:** each is marked honestly as *Works today*, *With a Module* (you connect an MCP server that does it), or *Planned*. `PRODUCT.md` forbids claiming capabilities the product does not have.
  - **Sell the hosted service, with no prices:** say what the hosted service is (we run it, your own Google key isn't needed, invite-only). No pricing line.
  - **Request access:** a `mailto:` link to a new setting, `CONTACT_EMAIL`. While the setting is empty, the button is hidden. (Petter's suggestion was `DEFAULT_TO_EMAIL`; renamed because Django's `DEFAULT_FROM_EMAIL` is the sender and `DEFAULT_TO_EMAIL` reads like a default recipient for every email.)
  - **Log in:** a link to the Portal login.
  - **Self-host it:** a link to the public repo, https://github.com/irma-AI/Voice, at the README's Self-host section.
- **Showing the Portal:** no screenshots. Petter: "i dislike screenshots, that feels outdated." The Portal's look isn't decided yet, so the landing page ships first without a Portal showcase. The Portal ticket adds one later, built from the Portal's finished components.
- **Order:** the landing page is built first, before the Portal (Petter's choice over Portal first).

## 2. Portal

- Every existing page, restyled phone first: login, the password reset flow, dashboard, settings, Modules, calls and the operator totals page. No new features beyond the Theme fields below.
- Owners use it phone first, between jobs; desktop is secondary (`PRODUCT.md`).
- **Theme fields, on the settings page:**
  - A logo upload: PNG, WebP or JPEG, up to about 256 KB, stored in Postgres (the only data store, ADR 0002). No SVG, because SVG can carry script. No object storage (that would be a new vendor).
  - One accent colour. Voice adjusts it so text on it still meets WCAG 2.2 AA.
  - With no Theme set, the Caller sees Voice's own look.
- Adds the Portal showcase to the landing page once its components exist (see above).

## 3. Call page

- **Where it lives now:** the core serves it, and since VOI-71 it opens only inside a frame on the Business's own website (the saved Website domain, `frame-ancestors`). VOI-73 (in progress in another session) builds the loader script, the launcher and the panel. This redesign **styles what VOI-73 ships**, and its ticket waits on VOI-73.
- **Identity:** per-Business Theme (Petter chose this over the Business name set in Voice's style). The Business's logo and accent colour show on the page. This changes the rule in `CONTEXT.md` and `PRODUCT.md`: a Business's settings are now a name, free-text facts, languages and a Theme.
- **Language:** English page text for now (Petter: "English for now as it's open source and agnostic but we should probably add translations"). The agent still speaks the Business's languages.
- **Disclosure in writing:** shown before the Caller presses start and for the whole call. Petter approved the English line on 2026-10-17, verbatim: "You are talking to an AI assistant." The agent keeps saying the Swedish line ("Du pratar med en AI-assistent.") aloud on Swedish calls. Design places these lines and never rewords them.
- **During a call:** who is speaking (agent or Caller) and a **Live transcript** of both sides. Shown only, never kept, and not part of the Call record.
  - Fact checked 2026-10-17: Pipecat 1.12.0's Gemini Live service already has input and output transcription switched on (`pipecat/services/google/gemini_live/llm.py:1340-1341`). The Caller's words arrive as `TranscriptionFrame` upstream and the agent's as `LLMTextFrame`/`TTSTextFrame` downstream. The core only has to forward them to the page over the existing WebSocket. Whether transcription adds to Gemini's bill is **not checked**: cost is read only from usage tokens (`voice/cost.py`), and the code doesn't show whether Google counts transcription in them.
- **States to design:** start, connecting, live, ended, microphone blocked, couldn't connect, and refused (an expired or wrong link, or a wrong site). The panel is small and sits inside someone else's page.

## 4. Call button

- Superseded during the grilling: Petter first picked a styled `<a>` with no script, but main had already moved to the Intercom-style loader in VOI-69/VOI-73 (a script snippet, a launcher button on the Business's site, the call page in a panel).
- The redesign styles the launcher and the panel in the shared world with the Business's Theme. It must not break or be broken by the host page's own styles.

## Build order

1. Shared tokens and base, from `DESIGN.md`.
2. Landing page.
3. Portal, including the Theme fields and the landing page's Portal showcase.
4. Call page, launcher and panel, after VOI-73.

## Related tickets

- VOI-67: translations for the Portal, landing and call page, blocked by VOI-76.
- VOI-76: research the translation framework and how the core shares strings with the Portal.
- VOI-69 / VOI-73: the embedded Call button and panel.

## Not decided here

- The visual world itself: impeccable new-work, next.
- How the landing page shows the Portal: decided in the Portal ticket.
- Whether Live transcript costs more on Gemini's bill: not checked.
