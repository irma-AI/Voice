# How Google says to prompt the Live model for tool use

Read 2026-10-18 for VOI-142 (the agent skipped a connected search tool). The pages were read through a summarising fetch, so the quotes below are the summary's, not checked against the page text; re-read the pages before relying on a wording.

## What the pages say

- [Live API: tool use](https://ai.google.dev/gemini-api/docs/live-api/tools) (read 2026-10-18): tools go in the session config as `function_declarations`; a call is BLOCKING by default (the model does not answer until the tool response is sent), NON_BLOCKING is set per declaration. The page has no guidance on how to word a system instruction for tools. It names Gemini 3.1 Flash Live and 2.5 Flash Live, not the model we run (`gemini-3.8-live`), so Pipecat's own handling of 3.8 (`pipecat/services/google/gemini_live/llm.py`, `_tag_tool_behaviors`) is what we follow for the behaviour flag.
- [Live API: best practices](https://ai.google.dev/gemini-api/docs/live-api/best-practices) (read 2026-10-18): order the system instruction as persona, conversational rules, guardrails; "Specify tool calls within a flow in distinct sentences"; "Be sure to tell Gemini under what conditions a tool call should be invoked"; each function definition should carry "names, descriptions, parameters, and invocation conditions"; guardrails work as "if this happens, do that"; "unmistakably" makes an instruction firmer; the model "performs best on tasks with single function calls".
- [Function calling](https://ai.google.dev/gemini-api/docs/function-calling) (read 2026-10-18, first 100,000 of 146,490 characters): `auto` lets the model decide whether to call; the best-practices part was in the unread rest.

## What it means for our prompt

- The failure matches the "conditions" advice: the prompt's guardrail "answer only from the business facts, otherwise say you don't know" came first and the condition for using a tool came after it, so the model took the guardrail. The prompt now names a tool's result as a source in that same rule, and the tools paragraph gives the condition in its own sentence.
- A Module author owns the tool's description, so "invocation conditions" belong there (Exa's description says "Best for: ..."); the core cannot add them.
- Not read: the unread tail of the function-calling page, and anything specific to `gemini-3.8-live`.
