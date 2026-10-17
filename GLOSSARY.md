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
The business whose calls the agent answers, with its own facts and Modules. One Business is one Portal account. Its settings are a name, free-text facts, languages and a Theme; anything more structured for the agent comes as a Module, never as a fixed Portal field.
_Avoid_: tenant, customer, clinic, client, agency

**Call link**:
A Business's public address (`/call/<unguessable>/` on the Portal) where anyone can start a call with its settings.
_Avoid_: public URL, widget

**Call button**:
A link a Business pastes into its own website, from a snippet on its dashboard. It opens the Business's call link in a new window.
_Avoid_: widget, embed

**Website domain**:
The registrable domain of a Business's own website (`example.se` for `www.shop.example.se`), saved in its Portal settings. The Portal holds it and puts it on a Call link's ticket, so the call page can be framed only by that site; the agent's settings do not carry it.
_Avoid_: site, URL, host

**Theme**:
A Business's logo and one accent colour, shown to its Callers on the call page and the Call button. The Portal and Voice's own pages keep Voice's look.
_Avoid_: branding, skin, white-label

**Live transcript**:
The words of a call shown to the Caller on the call page while it runs, for both sides. Shown only, never kept: it is not part of the Call record.
_Avoid_: transcript log, captions

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
