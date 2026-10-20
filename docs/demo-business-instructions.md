# Demo Business: instructions

The instructions for the demo Business whose Call button the landing page carries (VOI-244). Petter pastes them into that Business's settings page himself; no code reads this file.

They are facts only. The core's prompt (`system_instruction` in `voice/agent.py`) already makes the agent "Kim, the AI assistant who answers the phone for" the Business's name, opens every call with the greeting and the AI disclosure, keeps it warm and brief, answers only from these facts, never states a price that is not here, and says it cannot book. So the text names no persona and repeats no rule: a second "you are" here would give the agent two identities. Name the Business "Voice" in its settings, since the greeting says "välkommen till" that name.

Everything below works today unless it is named as planned. It makes no claim about what is kept: that is caller wording, the privacy notice's (`/privacy/`).

## Paste this (English)

```text
About this call: the caller is a visitor trying Voice from the Call button on the Voice website. This call is itself the demo, and it ends after three minutes. This demo has no Modules connected, so it shows answering from instructions, not Actions.

What Voice is: an AI voice agent that answers a business's callers on the business's own website, in Swedish or English, from the business's own instructions.

How a business uses it:
The Portal: the business logs in, writes instructions for its agent the way it would brief a new colleague (opening hours, services, prices, how to treat callers), chooses Swedish, English or both, and adds a logo and accent colour. Changes apply from the next call.
Test call: one button in the Portal opens a call with the saved settings, so the business can try its agent at once.
The Call button: the business saves its website address and gets a short tag to paste into its page. Visitors press the button and talk to the agent in the browser, with nothing to install. The call opens only from the business's own website.
Modules and Actions: the business connects services that speak MCP, a booking system for example. Each Module gives the agent Actions it can take during a call, such as finding a free time or moving a booking, while the caller is still on the line.
Call history: the business sees when each call came in and how long it lasted.

Planned, not built yet: putting a caller through to a person, phone calls (not only the website), and letting the business's own AI agents do everything the Portal can.

Getting Voice: access is by invitation, through the Request access button on the Voice website. The code is open, so anyone can also run Voice on their own server with their own Google key. Prices are not public; they are settled when a business gets in touch.
```
