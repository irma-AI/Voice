# How Google says to prompt the Live model for tool use

Read 2026-10-18 for VOI-142 (the agent skipped a connected search tool). The pages were read through a summarising fetch, so the quotes below are the summary's, not checked against the page text; re-read a page before relying on a wording.

## What the pages say

- [Live API: tool use](https://ai.google.dev/gemini-api/docs/live-api/tools) (read 2026-10-18): tools go in the session config as `function_declarations`; a call is BLOCKING by default (the model does not answer until the tool response is sent), NON_BLOCKING is set per declaration. The page has no guidance on how to word a system instruction for tools. It names Gemini 3.1 Flash Live and 2.5 Flash Live, not the model we run (`gemini-3.8-live`); the capabilities guide below covers that one.
- [Live API: best practices](https://ai.google.dev/gemini-api/docs/live-api/best-practices) (read 2026-10-18): order the system instruction as persona, conversational rules, guardrails; "Specify tool calls within a flow in distinct sentences"; "Be sure to tell Gemini under what conditions a tool call should be invoked"; each function definition should carry "names, descriptions, parameters, and invocation conditions"; guardrails work as "if this happens, do that"; "unmistakably" makes an instruction firmer; the model "performs best on tasks with single function calls".
- [Function calling](https://ai.google.dev/gemini-api/docs/function-calling) (read 2026-10-18, whole page): `auto` lets the model decide whether to call. Best practices: "Be clear and specific" in descriptions, descriptive names, strong types, "Keep active set to 10-20 tools maximum" (our `MAX_ACTIONS` is 20), "Provide context and instructions", validate calls before executing. Nothing on system-instruction wording, and nothing on a model answering from memory instead of calling.
- [Live API: capabilities guide](https://ai.google.dev/gemini-api/docs/live-guide) (read 2026-10-18): `gemini-3.8-live` supports function calling, with `behavior: NON_BLOCKING` or `BLOCKING` (which one is the default is unclear on the page; Pipecat declares BLOCKING for our synchronous tools), and does not support `thinkingLevel`. `gemini-3.8-live-extended-thinking` is NON_BLOCKING only. Nothing on system-instruction handling for tools.

## What it means for our prompt

- Reading the whole page changed nothing in the fix.
- The failure matches the "conditions" advice: the prompt's guardrail "answer only from the business facts, otherwise say you don't know" came first and the condition for using a tool came after it, so the model took the guardrail. The prompt now names a tool's result as a source in that same rule, and the tools paragraph gives the condition in its own sentence.
- A Module author owns the tool's description, so "invocation conditions" belong there (Exa's description says "Best for: ..."); the core cannot add them.
- Not found in any page: wording advice for a system instruction that stops a model answering from memory, so the second prompt sentence rests on the eval runs, not on Google's text.
