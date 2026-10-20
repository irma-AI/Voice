# The agent endpoint with a real Claude Code (VOI-118)

Run on 2026-10-20 against a local Portal (`portal.settings`, `DEBUG=1`) built from the VOI-118 branch, with Claude Code 2.1.281 (`claude -p`, model haiku, `--mcp-config` with `--strict-mcp-config`, so the user's own Claude settings were not touched). Not production: production gets this code with its deploy, and is not checked here.

## What was seen

- **The connection line**, as the Access tokens page shows it, was accepted by `claude mcp add` (run with `-s project` in a scratch folder, so it wrote only that folder's `.mcp.json`; the tools were then driven through `--mcp-config` with the same address and header. The line exactly as pasted, with its default scope, is not checked).
- **A read-only token** listed five tools: `check_module`, `get_call_button`, `list_modules`, `list_recent_calls`, `read_settings`. Asked to call `change_settings`, Claude Code said the tool is not available. The same call sent by hand got the SDK's `Unknown tool: change_settings`.
- **A full token** listed ten: the five above and `add_module`, `change_business_details`, `change_settings`, `get_test_call_link`, `remove_module`.
- **An operator's full token** called every Command once, through Claude Code: all answered as designed. `get_call_button` refused with its plain reason (no website saved). `change_business_details`, `remove_module` and `invite_business` answered `staged: true` with a preview. `get_test_call_link` gave a link with an `agent_test` ticket. `check_module` said the example address could not be reached (its 2 s deadline). `list_totals` answered an empty list (no Call records yet).

## Not checked

- Production, and a token made on the production Portal.
- Sign-in with a click from any real client (claude.ai, ChatGPT, Grok, Gemini, Claude Code's own `/mcp` sign-in): VOI-120, which needs Petter's accounts.
- Other clients that take a pasted header (Cursor, scripts in other languages).
- How each client shows the tool hints (read-only, destructive).
