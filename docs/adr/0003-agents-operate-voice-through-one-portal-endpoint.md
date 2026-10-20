# A Business's own agent operates Voice through one MCP endpoint, with an Access token

Status: accepted (Petter, 2026-10-20: the official SDK plus `django-stateless-mcp`, inside the Portal; `DECISIONS.md`)

Every thing a person can do in the Portal is also a Command a Business's own agent can send over MCP (PRODUCT.md principle 2), through one endpoint of the Portal, calling the same functions as the Portal pages. The agent signs in with an Access token that a person makes on the Portal page: read-only or full, one Business each; the operator's token additionally sees the operator Commands. The tool list a client sees follows its token, and a hidden Command is refused if called anyway.

## Considered Options

- FastMCP 4 as the server: best built-in per-tool access, but a new dependency tree and the Portal would move from gunicorn/WSGI to an async server for one endpoint.
- Strands Agents: an agent framework that only consumes MCP servers; it cannot serve one.
- Separate endpoints for Business and operator: stronger isolation, but two connectors for the operator; one endpoint with a filter and a test over every Command and token kind was chosen.
- OAuth sign-in only: connects claude.ai and ChatGPT with a click, but is a large security-sensitive build; pasted tokens ship first and the sign-in follows as the last group of tickets.

## Consequences

- The official MCP SDK (already locked) with the `django-stateless-mcp` glue, pinned. Both are young, so the Commands live in one module that a move to another framework or host only relocates. Research: `docs/research/mcp-server-framework.md`.
- A new way in for a Business's data, so the database refuses what a token must not do: a closed set of scopes, a hash and never the secret, and an append-only record of every Command (name, token, time, result; never the values).
- The core has no Commands: it takes no actions (ADR 0001), keeps nothing a Business edits, and no core action was found that an agent would need.
- The call app and the Portal stay separate services (ADR 0002 stands; Petter, 2026-10-18).
