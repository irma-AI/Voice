"""The example Module: a tiny MCP server with one Action, for a Module author to copy and for the eval to prove the path.

Run it as `python -m modules.example` (stdio), the way a self-hosted Business adds a local Module:
{"name": "hours", "command": "python", "args": ["-m", "modules.example"]}.
It holds no credentials and reaches nothing; a real Module holds its own.
"""

from mcp.server.mcpserver import MCPServer

# Not the eval Business's own hours, so an answer with these closing times can only have come from the Action.
HOURS = "måndag till fredag 09-19, lördag 10-15, söndag stängt"

server = MCPServer("example")


@server.tool()
def opening_hours() -> str:
    """The Business's opening hours."""
    return HOURS


if __name__ == "__main__":
    server.run()
