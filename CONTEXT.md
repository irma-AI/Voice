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
A Business's public address (`/call/<unguessable>/` on the Portal) where anyone can start a call with its settings.
_Avoid_: public URL, widget

**Call button**:
A button a Business pastes into its own website with a snippet from the Portal. It opens the call page for that Business, and works only from the website addresses the Business lists.
_Avoid_: widget, embed

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
