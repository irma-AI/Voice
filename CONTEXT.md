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
The business whose calls the agent answers, with its own facts and Modules. One Business is one Portal account. Its settings are a name, free-text facts and languages; anything more structured for the agent comes as a Module, never as a fixed Portal field.
_Avoid_: tenant, customer, clinic, client, agency

**Call link**:
The address (`/call/<unguessable>/` on the Portal) a Business's Call button opens in its panel. It starts a call with the Business's settings only for a page loaded in a frame, and only once the Business has saved a Website domain; in a tab, or pasted anywhere else, it refuses a browser that says so (a script can send the header; not enforced).
_Avoid_: public URL, widget

**Call button**:
A button on a Business's own website, added with a script tag from its dashboard (shown once a Website domain is saved). A launcher sits in the corner of the page; pressing it opens the Call link in a panel on that page, and pressing it again ends the call. Browsers are told to let only the Website domain and its subdomains show it (not seen in a real browser yet).
_Avoid_: widget, embed

**Website domain**:
The registrable domain of a Business's own website (`example.se` for `www.shop.example.se`), saved in its Portal settings. The Portal holds it and puts it on a Call link's ticket, so the call page can be framed, and the Call button used, only on that site; the agent's settings do not carry it.
_Avoid_: site, URL, host

**Test call**:
A call a Business starts from its own Portal to try its agent. Every other call comes through its Call link.
_Avoid_: demo call, trial call

**Call record**:
What one call that reached the model used: when it started, how long it ran, what the model used and what that cost, and whether it was a Test call or came through the Call link. Never the words or the audio, and never changed once kept.
_Avoid_: usage log, call log, CDR

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

**Portal**:
The web app where a Business logs in to set its Modules and general settings. It ships in both the open code and the hosted service.
_Avoid_: dashboard (only one page of it), admin
