"""The Portal's side of a Business's Modules: what an address may be, and what a Module offers.

A Module is an MCP server (ADR 0001). The Portal stores its name and address only and holds no password of any
Module (CLAUDE.md § Hard rules 1); the Modules page connects to each Module to list the Actions it offers. The
Portal never imports voice/: the address rule below is the core's (voice/modules.py `address_problem`) as a second
copy, and tests/test_modules.py reads both and fails if they disagree.
"""

import asyncio
import ipaddress
import re
import shlex
import socket
from collections.abc import Sequence
from typing import NamedTuple
from urllib.parse import urlsplit

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client

# Edit with contract/business-settings.schema.json: tests/portal/test_settings_contract.py fails on drift.
MODULES_MAX = 10
NAME_MAX = 100
URL_MAX = 2000
COMMAND_MAX = 500
ARGS_MAX = 20
ARG_MAX = 500
# An address with no user, password, query or fragment: those are where a credential would sit. The database refuses
# anything else (the constraint in models.py uses this pattern).
URL_PATTERN = r"^https?://[^/?#@]+(/[^?#]*)?$"
# ponytail: the page waits this long in silence for a Module; make it a setting if a real Module is slow.
PROBE_TIMEOUT_S = 5

Action = tuple[str, str]  # the Action's name and its description


class Offer(NamedTuple):
    """What asking one Module gave: its Actions, or the sentence saying why it could not be asked."""

    actions: list[Action]
    problem: str | None = None


Spec = tuple[str, str, Sequence[str]]  # a Module's url, command and args


def address_problem(url: str) -> str | None:
    """Why a remote Module's address may not be used on the hosted service, or None: https, and public addresses only."""
    parts = urlsplit(url)
    host = parts.hostname
    if parts.scheme != "https" or not host:
        return "Use an https address."
    try:
        found = socket.getaddrinfo(host, parts.port or 443, type=socket.SOCK_STREAM)
    except (OSError, ValueError):
        return "That address does not resolve."
    # ponytail: checked now, connected a moment later, so a DNS answer that changes between the two gets through; pin the checked address if that ever matters.
    if not all(ipaddress.ip_address(f[4][0]).is_global for f in found):
        return "That address is not on the public internet."
    return None


def parse_address(text: str, allow_local: bool) -> tuple[str, str, list[str]]:
    """The (url, command, args) a typed address means; raises ValueError with the sentence to show.

    A web address is a remote Module. Anything else is a command line for a local Module, which only a
    self-hosted Portal (`allow_local`) accepts, and self-hosting also accepts http and private addresses.
    """
    text = text.strip()
    if text.lower().startswith(("http://", "https://")):
        if len(text) > URL_MAX or not re.fullmatch(URL_PATTERN, text):
            raise ValueError(
                "That is not a plain address. Leave out any password, key or ?query: a Module keeps its own credentials."
            )
        if not allow_local and (why := address_problem(text)):
            raise ValueError(why)
        return text, "", []
    if not allow_local:
        raise ValueError(
            "Give the Module's https address, like https://example.com/mcp. Local Modules work only on a self-hosted Portal."
        )
    try:
        words = shlex.split(text)
    except ValueError:
        raise ValueError("Could not read that as a command.") from None
    if (
        not words
        or len(words[0]) > COMMAND_MAX
        or len(words) - 1 > ARGS_MAX
        or any(len(w) > ARG_MAX for w in words)
    ):
        raise ValueError("That command is empty or too long.")
    return "", words[0], words[1:]


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
