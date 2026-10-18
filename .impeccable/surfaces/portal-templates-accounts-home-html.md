---
version: 1
slug: "portal-templates-accounts-home-html"
primary_target: "portal/templates/accounts/home.html"
related_targets: []
---

# Landing page

Scope: the Portal's logged-out `/` (`portal/templates/accounts/home.html`), the first surface of the four-surface redesign (`docs/design/four-surface-redesign.md`). Visitor mode: Persuade.

Audience: small Swedish business owners first (phone first), self-hosters second. Action: Request access (mailto `CONTACT_EMAIL`), Log in, Self-host it. Proof: the call itself, shown working; no customers, prices or numbers exist and none are invented. Unbuilt capabilities carry a small "Planned" label.

## Direction contract

THESIS: One call, drawn as it happens. A precise ring is the call: time fills it, the conversation runs inside it, and each step the agent takes lands on it as a dot. It refuses the category's hero of a headline beside a phone or dashboard mockup, and refuses metaphor that needs explaining.

OWN-WORLD: Blue hour #1A2A44 to Deep sea #0B1322 ground, Foam #FFFFFF type, Granite #3A3F47 lines and track, Cable light #F5D9A8 only on what is live (the progress arc, the active dot, the Agent's words). A refined high-contrast serif for headline and spoken lines, a clean modern sans for labels. Hairline geometry, tick marks, small hollow dots, no cards, no photos, no glow.

STORY: The visitor sees a real call play out: a Caller asks, the agent reads the Business's instructions, uses a Module over MCP to move a booking, answers, and hands the Caller to a person when asked (Planned). They understand it talks, acts and connects, and they press Request access.

FIRST VIEWPORT: Desktop: left column, headline "Voice for the agentic company." large serif, the MCP-once subline, white pill Request access and link Open code · Self-host it. Right, larger: the ring with 120 ticks; a warm arc fills clockwise over a 40+ second loop; inside, a speaker line that moves with whoever is speaking (Foam for Caller, Cable light for Agent) and the current and previous line beside it; step dots appear on the ring with label and italic note (Caller, Instructions, Agent, MCP · Bookings, Human · Planned with a dashed exit). Phone: the ring becomes a vertical rail down the right edge beside the title and text, filling downward with the same dots; the current step, a small speaker line and the live line sit in a block under the buttons. It plays on load and a Pause control is always present; under reduced motion it plays in turn, the arc and rail fill steadily and the speaker line holds still (VOI-99, VOI-105).

FORM: Turn, an instrument ring that is the call. My own grounded candidate (not on the dealt list; derived by brainstorm agents from the product's call flow), position 1 on the ordered list after Call Score, Live Line and Mid-Sentence were folded into it. The concept roll was skipped: no `seed:` reference was made for this direction (open finish-review finding, 2026-10-18). Reference: the live prototype built in this session, kept at `.impeccable/mocks/turn-prototype.html`.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

## Unresolved

- The conversation script (a longer call: move a booking, then ask to be put through to a person). Petter writes it later.
- AA contrast of the palette (`docs/design/four-surface-redesign.md`).
- The line label "MCP" against the product's term "Modules". ("Instructions" is now the product's own term, VOI-107.)
