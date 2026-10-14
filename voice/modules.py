"""The Actions port: where the core gets what the agent can do during a call.

A Module is an MCP server (ADR 0001). At call start `connect_modules` connects to each of the Business's
Modules, and the Actions they offer go to the model as its tools; Gemini Live fixes its tool list when the
call starts, so this runs once per call. A Module that cannot be used is skipped and logged, never fatal:
the call goes on without it. The core never imports a Module, and a Module never imports the core.
"""

import asyncio
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from loguru import logger
from mcp import StdioServerParameters
from mcp.client.session_group import StreamableHttpParameters
from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.services.mcp_service import MCPClient

from voice.settings import Module

# ponytail: a call waits this long in silence for a Module before it goes on without it; make it a setting if a real Module is slow.
MODULE_TIMEOUT_S = 5


# ponytail: one cap for the whole call; the right size is unknown until a real Business has several Modules.
MAX_ACTIONS = 20


class ModuleSkipped(Exception):
    """This Module is not used on this call. The message goes in the log, so it holds no address and no secret."""


def local_modules_allowed(env: Mapping[str, str] = os.environ) -> bool:
    """A local Module is someone's program run on this machine: only where self-hosting says so (hosted never does)."""
    return env.get("ALLOW_LOCAL_MODULES", "").strip() == "1"


@dataclass
class Connected:
    """The Actions the call may offer and the connections behind them. `close` ends every connection, however the call ends."""

    actions: list[FunctionSchema] = field(default_factory=list[FunctionSchema])
    clients: list[MCPClient] = field(default_factory=list[MCPClient])

    async def close(self) -> None:
        for client in (
            self.clients
        ):  # close() is safe to repeat: Pipecat also closes them at call end
            await client.close()


async def _actions(
    module: Module, allow_local: bool, timeout: float, connected: Connected
) -> list[FunctionSchema]:
    if module.command is not None:
        if not allow_local:
            raise ModuleSkipped("a local Module is not allowed here")
        params = StdioServerParameters(command=module.command, args=list(module.args))
    elif module.url is not None:
        params = StreamableHttpParameters(url=module.url)
    else:  # settings.parse gives a Module a url or a command; refuse anything else
        raise ModuleSkipped("a Module has neither an address nor a command")
    client = MCPClient(params)
    try:
        tools = await asyncio.wait_for(client.tools(), timeout)
    except BaseException:
        await client.close()
        raise
    connected.clients.append(client)
    return tools.standard_tools  # pyright: ignore[reportReturnType]  # the client only builds FunctionSchemas


def admit(
    actions: Sequence[FunctionSchema], offered: Sequence[FunctionSchema]
) -> tuple[list[FunctionSchema], list[str]]:
    """The offered Actions that may join `actions`, and the names of those that may not.

    A name already taken is refused, so a call never goes to the wrong Module and Gemini never sees two
    declarations of one name; so is anything past MAX_ACTIONS, so a Module cannot swell the call's setup.
    """
    names = {a.name for a in actions}
    kept: list[FunctionSchema] = []
    dropped: list[str] = []
    for action in offered:
        if action.name in names or len(actions) + len(kept) >= MAX_ACTIONS:
            dropped.append(action.name)
        else:
            names.add(action.name)
            kept.append(action)
    return kept, dropped


async def connect_modules(
    modules: Sequence[Module],
    allow_local: bool = False,
    timeout: float = MODULE_TIMEOUT_S,
) -> Connected:
    """The Actions of every Module that could be used, each with the call handler that reaches its Module.

    The caller closes the result when the call ends, whatever ends it. A skipped Module is logged by
    name and the kind of failure only: its address could hold a password. Actions `admit` refuses are
    dropped and logged by name.
    """
    connected = Connected()
    try:
        results = await asyncio.gather(
            *(_actions(m, allow_local, timeout, connected) for m in modules),
            return_exceptions=True,
        )
        for module, result in zip(modules, results, strict=True):
            if isinstance(result, BaseException):
                why = (
                    str(result)
                    if isinstance(result, ModuleSkipped)
                    else type(result).__name__
                )
                logger.error("Module {!r} skipped: {}", module.name, why)
                continue
            kept, dropped = admit(connected.actions, result)
            connected.actions += kept
            for name in dropped:
                logger.error("Module {!r} skipped its Action {!r}", module.name, name)
    except BaseException:
        await connected.close()  # cancelled mid-connect: the Modules that did connect must not outlive the call
        raise
    return connected
