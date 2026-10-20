# Voice

The voice core: it connects a phone or browser call to a live AI voice model and runs the call.

## Language

**Caller**:
The person on the other end of a call, inbound or outbound.
_Avoid_: user, patient, customer

**Channel**:
A way a caller reaches the core: phone, web or eval.
_Avoid_: entrance, transport

**Hand-off**:
Passing a call to a person, or taking a message, when the agent cannot finish it.
_Avoid_: transfer, escalation

**Business**:
The business whose calls the agent answers, with its own Instructions and Modules. One Business is one Portal account. Its settings are a name, Instructions, languages and a Theme; anything more structured for the agent comes as a Module, never as a fixed Portal field.
_Avoid_: tenant, customer, clinic, client, agency

**Instructions**:
A Business's free text for its agent, in its own words: what the agent should know about the business and how it should act. The agent answers only from it and its Modules' Actions.
_Avoid_: facts, prompt, knowledge base

**Call link**:
The address (`/call/<unguessable>/` on the Portal) a Business's Call button opens in its panel. It starts a call with the Business's settings only for a page loaded in a frame, and only once the Business has saved a Website domain; in a tab, or pasted anywhere else, it refuses a browser that says so (a script can send the header; not enforced).
_Avoid_: public URL, widget

**Call button**:
A button on a Business's own website, added with a script tag from its dashboard (shown once a Website domain is saved). A launcher sits in the corner of the page; pressing it opens the Call link in a panel on that page, and pressing it again ends the call. Browsers are told to let only the Website domain and its subdomains show it (seen in desktop Chromium and on one iPhone, not on Android).
_Avoid_: widget, embed

**Website domain**:
The registrable domain of a Business's own website (`example.se` for `www.shop.example.se`), saved in its Portal settings. The Portal holds it and puts it on a Call link's ticket, so the call page can be framed, and the Call button used, only on that site; the agent's settings do not carry it.
_Avoid_: site, URL, host

**Theme**:
A Business's logo and one accent colour, shown to its Callers on the call page and the Call button. The Portal and Voice's own pages keep Voice's look.
_Avoid_: branding, skin, white-label

**Live transcript**:
The words of a call shown to the Caller on the call page while it runs, for both sides. Shown only, never kept: it is not part of the Call record.
_Avoid_: transcript log, captions

**Test call**:
A call a Business starts from its own Portal to try its agent. Every other call comes through its Call link.
_Avoid_: trial call

**Demo call**:
A visitor's call from Voice's own landing page, through the demo Business's Call link, cut at 3 minutes where every other call gets 10. Counts toward that Business's daily budget. Nothing starts one yet (VOI-244).
_Avoid_: trial call, public call

**Call record**:
What one call that reached the model used: when it started, how long it ran, what the model used and what that cost, and whether it was a Test call, a Demo call or came through the Call link. Never the words or the audio, and never changed once kept.
_Avoid_: usage log, CDR

**Call log**:
Everything stored about one call's events (for now its Barge-in timings, levels and scores, and what the Caller's browser applied), kept 30 days from the call's start and then deleted. Not the Call record, which stays final and is kept for billing.
_Avoid_: event log, call history, trace

**Barge-in**:
The Caller speaking while the agent talks, so the agent stops. A false barge-in is one where no words followed, usually noise.
_Avoid_: interruption, cut-off

**Scenario**:
A scripted call on the eval channel: the caller's lines and what the checks expect.
_Avoid_: test case, script

**Module**:
An MCP server that offers Actions to the core. A Business adds, combines or swaps its Modules; the core does nothing by itself beyond the call.
_Avoid_: plugin, integration, connector

**Action**:
One thing a Module lets the agent do during a call, such as looking up a booking.
_Avoid_: tool (in everyday talk), function

**Command**:
One thing a Business's own agent can tell Voice to do, such as changing its facts or removing a Module, over MCP. Each is something a person can already do in the Portal. Not an Action, which is what the voice agent does during a call.
_Avoid_: tool (in everyday talk), Action, API call

**Command record**:
The Portal's note of one Command an assistant sent: which Command, with which Access token, when, and whether it was done, refused, failed or timed out. Never what it was asked or answered. Never changed or deleted.
_Avoid_: audit log, history

**Pending change**:
A change a destructive Command asked for, waiting for the Business to approve or reject it in the Portal. Nothing changes before the approval; it expires after 7 days, and revoking the Access token that asked for it cancels it. Removing a Module is one, and so is changing the Business's name, instructions or languages.
_Avoid_: staged operation, draft

**Access token**:
The secret a Business makes in its Portal and pastes into its own AI assistant (its own agent), so the assistant can send Commands. In Portal copy the owner's tool is "your AI assistant"; "your agent" is always the voice agent. It is read-only or full, chosen when it is made, and works for that one Business.
_Avoid_: API key, password

**Portal**:
The web app where a Business logs in to set its Modules and general settings. It ships in both the open code and the hosted service.
_Avoid_: dashboard (only one page of it), admin
