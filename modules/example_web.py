"""A web-search example Module: one general-purpose Action, as a real search Module such as Exa offers.

Stands in for a search Module the eval can hold still: the `module_web` Scenario proves the agent uses it for a
question the Business's instructions do not cover. Run it as `python -m modules.example_web` (stdio). It reaches nothing.
"""

from mcp.server.mcpserver import MCPServer

# Not the real height of the tower (155 m), so an answer with this figure can only have come from the Action.
HEIGHT = 123
ANSWER = f"Kaknästornet i Stockholm är {HEIGHT} meter högt."

# The Action's name, which the eval's check looks for in the call record.
ACTION = "web_search"

server = MCPServer("example_web")


@server.tool(name=ACTION)
def web_search(query: str) -> str:
    """Search the web for any topic and get clean, ready-to-use content. Best for: finding current information, news, facts, people, companies, or answering questions about any topic."""
    return ANSWER


if __name__ == "__main__":
    server.run()
