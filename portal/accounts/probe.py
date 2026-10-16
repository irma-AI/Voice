"""Asking a Module what it offers: the Modules page connects to each Module over MCP and lists its Actions.

The address rule (portal/accounts/modules.py) is applied first on the hosted service, so the Portal never connects
to an address the core would refuse.
"""

import asyncio
from collections.abc import Sequence
from typing import NamedTuple

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client

from portal.accounts.modules import address_problem

# ponytail: the page waits this long in silence for a Module; make it a setting if a real Module is slow.
PROBE_TIMEOUT_S = 5

Action = tuple[str, str]  # the Action's name and its description


class Offer(NamedTuple):
    """What asking one Module gave: its Actions, or the sentence saying why it could not be asked."""

    actions: list[Action]
    problem: str | None = None


Spec = tuple[str, str, Sequence[str]]  # a Module's url, command and args


async def _probe(spec: Spec, allow_local: bool) -> Offer:
    url, command, args = spec
    if command and not allow_local:
        return Offer([], "A local Module is not allowed here.")
    if (
        url
        and not allow_local
        and (why := await asyncio.to_thread(address_problem, url))
    ):
        return Offer([], why)
    try:
        async with asyncio.timeout(PROBE_TIMEOUT_S):
            async with (
                (
                    stdio_client(
                        StdioServerParameters(command=command, args=list(args))
                    )
                    if command
                    else streamable_http_client(url)
                ) as (read, write),
                ClientSession(read, write) as session,
            ):
                await session.initialize()
                tools = (await session.list_tools()).tools
    except TimeoutError:
        return Offer([], f"It did not answer within {PROBE_TIMEOUT_S} seconds.")
    except Exception:  # noqa: BLE001  any failure is the same news for the Business; the address stays out of the message
        return Offer([], "It could not be reached, or it is not an MCP server.")
    return Offer([(t.name, t.description or "") for t in tools])


def what_they_offer(specs: Sequence[Spec], allow_local: bool) -> list[Offer]:
    """Asks every Module at once and returns their answers in order."""

    async def run() -> list[Offer]:
        return await asyncio.gather(*(_probe(s, allow_local) for s in specs))

    return asyncio.run(run())
