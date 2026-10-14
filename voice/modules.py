"""The Actions port: where the core gets what the agent can do during a call.

A Module is an MCP server (ADR 0001). At call start `connect_modules` connects to each of the Business's
Modules, and the Actions they offer go to the model as its tools; Gemini Live fixes its tool list when the
call starts, so this runs once per call. A Module that cannot be used is skipped and logged, never fatal:
the call goes on without it. The core never imports a Module, and a Module never imports the core.
"""

import asyncio
import os
from collections.abc import Mapping, Sequence

from loguru import logger
from mcp import StdioServerParameters
from mcp.client.session_group import StreamableHttpParameters
from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.services.mcp_service import MCPClient

from voice.settings import Module

# ponytail: a call waits this long in silence for a Module before it goes on without it; make it a setting if a real Module is slow.
MODULE_TIMEOUT_S = 5


class ModuleSkipped(Exception):
    """This Module is not used on this call. The message goes in the log, so it holds no address and no secret."""


def local_modules_allowed(env: Mapping[str, str] = os.environ) -> bool:
    """A local Module is someone's program run on this machine: only where self-hosting says so (hosted never does)."""
    return env.get("ALLOW_LOCAL_MODULES", "").strip() == "1"


async def _actions(
    module: Module, allow_local: bool, timeout: float
) -> tuple[MCPClient, list[FunctionSchema]]:
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
    return client, tools.standard_tools  # pyright: ignore[reportReturnType]  # the client only builds FunctionSchemas


async def connect_modules(
    modules: Sequence[Module],
    allow_local: bool = False,
    timeout: float = MODULE_TIMEOUT_S,
) -> list[FunctionSchema]:
    """The Actions of every Module that could be used, each with the call handler that reaches its Module.

    A skipped Module is logged by name and the kind of failure only: its address could hold a password.
    A second Action with a name already taken is dropped, so a call never goes to the wrong Module.
    """
    results = await asyncio.gather(
        *(_actions(m, allow_local, timeout) for m in modules), return_exceptions=True
    )
    actions: list[FunctionSchema] = []
    for module, result in zip(modules, results, strict=True):
        if isinstance(result, BaseException):
            why = (
                str(result)
                if isinstance(result, ModuleSkipped)
                else type(result).__name__
            )
            logger.error("Module {} skipped: {}", module.name, why)
            continue
        client, offered = result
        taken = {a.name for a in actions}
        for action in offered:
            if action.name in taken:
                logger.error(
                    "Module {} skipped its Action {}: the name is taken",
                    module.name,
                    action.name,
                )
            else:
                actions.append(action)
        if not any(a in actions for a in offered):
            await (
                client.close()
            )  # nothing of it reaches the model, so nothing would close it at call end
    return actions
