# The core takes no actions; Modules are MCP servers

The core runs the call and nothing else: every thing the agent can do during a call (look up, book, take a message) is an Action offered by a Module, which is an MCP server. A Business adds, combines or swaps Modules without touching the core. Local MCP servers are allowed in the open code; the hosted service accepts remote ones only, because a local one means running someone else's code.

## Considered Options

- Built-in connectors we maintain: fast for Businesses, but the core grows with every use case and stops being agnostic.
- Code plugins: simple to write, but cannot run in the hosted service without running untrusted code.
- Our own module format: full control, but a new standard nobody has servers for.

## Consequences

- Pipecat 1.12.0 ships an MCP client for local and remote servers. Gemini Live fixes its tool list when the call starts, so a call picks its Modules up front.
- A Module holds its own credentials; the Portal stores only its address.
