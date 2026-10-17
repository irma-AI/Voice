# Product

<!-- impeccable:product-schema 1 -->

Terms (Business, Caller, Module, Action, Call link, Test call, Call record): `CONTEXT.md`.

## Platform

web

## Users

- **Primary: small Swedish businesses on the hosted service.** An owner or staff member, not technical, who wants the business's calls answered. They are invited, set the agent up once (name, free-text facts, languages, Modules), try it with a Test call, paste a Call button on their website, and come back now and then to see recent calls.
- **Secondary: self-hosters.** Technical people who run their own copy with their own Google key and wire their own Modules (MCP servers).
- Owners use the Portal **phone first**, between jobs; desktop is secondary.
- **Callers** never see the Portal; they meet the product only on the call page, in Swedish by default.

## Product Purpose

Voice answers a Business's callers with a live AI voice agent, in Swedish or English, from the Business's own facts and the Actions its Modules offer. The Portal is where a Business sets that agent up and sees what its calls used. Success: a non-technical owner gets a working agent from their facts alone, and callers get their question answered or a clean Hand-off.

## Positioning

- **Open code.** The same core and Portal ship as the hosted service and as a self-hostable copy.
- **The core takes no actions.** Everything the agent can do in a call is an Action from a Module, an MCP server the Business adds, combines or swaps (ADR 0001).
- **Agent-operable by design (not built yet).** Every action a Business can take in the Portal or the core is also to be exposed to that Business as an MCP tool, so their own agents can run Voice as fully as a person in the Portal can. The user named Accounted as the model for this.

## Operating Context

- Access is by invitation only; there is no self-signup.
- The call page opens only from a Portal-made link: a Test call or the Business's Call link / Call button.
- Every call spends real Gemini credit; a Call record keeps what each call used and cost, never words or audio.
- The Portal and the call page are separate services; a Portal problem never cuts a live call (ADR 0002).

## Capabilities and Constraints

- Shipped: login, invite, password reset, settings (name, facts, languages), Modules, Test call, Call link and Call button snippet, recent calls, an operator totals page.
- A Business's settings stay a name, free-text facts and languages; anything more structured comes as a Module, never a fixed Portal field.
- Call languages: Swedish and English only.
- Portal UI language: English, because the code is open and language-agnostic. Translations, Swedish first, are planned (VOI-67).
- Stack: Django, Tailwind, htmx, Postgres (ADR 0002).
- Undecided: phone Channel (later), daily call limits (none yet), the MCP-tool surface for every Portal/core action (planned, see Positioning).

## Brand Commitments

- Name: Voice; the web app is the Portal.
- Caller-facing copy is Swedish and its legal wording (the AI disclosure "Du pratar med en AI-assistent.", caller notices) is fixed by Petter; never reword it in design work.
- Use `CONTEXT.md`'s terms in UI copy and avoid the words it lists under _Avoid_.

## Evidence on Hand

No customers, testimonials, case studies, usage numbers or pricing exist yet. Do not invent any.

## Product Principles

1. A non-technical owner finishes setup without help; anything technical lives behind a Module.
2. Everything a person can do, an agent can do too, through the same one way in.
3. Be plain about cost and limits: say what a call spends and what is not limited yet.
4. The call comes first: nothing in the Portal may slow or break a live call.

## Accessibility & Inclusion

The Portal and the call page meet WCAG 2.2 AA.
