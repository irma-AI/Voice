"""The Actions port, free: Modules connect at call start, and one that cannot be used never stops the call.

A real MCP server stands in for a Module (modules/example.py, over stdio), and a real socket for an
unreachable or hung one; nothing of ours is mocked.
"""

import asyncio
import json
import re
import socket
import sys
from collections.abc import Generator
from contextlib import closing, contextmanager
from pathlib import Path

from loguru import logger

from modules.example import HOURS
from tests.evals.checks import BUSINESS_FACTS, MODULE_BUSINESS_FILE
from voice.agent import system_instruction
from voice.modules import connect_modules, local_modules_allowed
from voice.settings import Module, Settings

EXAMPLE = Module("hours", command=sys.executable, args=("-m", "modules.example"))


@contextmanager
def logged() -> Generator[list[str]]:
    lines: list[str] = []
    sink = logger.add(lambda m: lines.append(str(m)), level="ERROR")  # pyright: ignore[reportUnknownLambdaType]
    try:
        yield lines
    finally:
        logger.remove(sink)


def names(*modules: Module, allow_local: bool = False, timeout: float = 5) -> list[str]:
    async def run() -> list[str]:
        actions = await connect_modules(modules, allow_local, timeout)
        return [a.name for a in actions]

    return asyncio.run(run())


def closed_port() -> int:
    with closing(socket.socket()) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_a_local_module_offers_its_action_where_self_hosting_allows_it() -> None:
    assert names(EXAMPLE, allow_local=True) == ["opening_hours"]


def test_a_local_module_is_never_started_where_self_hosting_does_not_allow_it(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "ran"
    code = f"open({str(marker)!r}, 'w')"
    sneaky = Module("sneaky", command=sys.executable, args=("-c", code))
    with logged() as log:
        assert names(sneaky, allow_local=True) == []  # started, but speaks no MCP
        assert marker.exists()
        marker.unlink()
        assert names(sneaky) == []  # the default is hosted: not allowed
    assert not marker.exists(), "a Module's program ran where local Modules are off"
    assert any("sneaky skipped: a local Module is not allowed" in m for m in log)


def test_local_modules_are_off_unless_the_environment_says_so() -> None:
    assert not local_modules_allowed({})
    assert not local_modules_allowed({"ALLOW_LOCAL_MODULES": "true"})
    assert local_modules_allowed({"ALLOW_LOCAL_MODULES": "1"})


def test_an_unreachable_module_is_skipped_logged_and_does_not_stop_the_others() -> None:
    dead = Module("dead", url=f"http://user:pw@127.0.0.1:{closed_port()}/mcp")
    missing = Module("missing", command="no-such-program-voice")

    with logged() as log:
        assert names(dead, missing, EXAMPLE, allow_local=True) == ["opening_hours"]
    text = "".join(log)
    assert "Module dead skipped" in text and "Module missing skipped" in text
    assert "pw" not in text, "a Module's address could hold a password"


def test_a_module_that_never_answers_is_given_up_on() -> None:
    with closing(socket.socket()) as hung:
        hung.bind(("127.0.0.1", 0))
        hung.listen()
        url = f"http://127.0.0.1:{hung.getsockname()[1]}/mcp"
        with logged() as log:
            assert names(Module("hung", url=url), timeout=0.5) == []
    assert any("Module hung skipped" in m for m in log)


def test_a_second_action_with_a_taken_name_is_dropped() -> None:
    twin = Module("twin", command=sys.executable, args=("-m", "modules.example"))

    with logged() as log:
        assert names(EXAMPLE, twin, allow_local=True) == ["opening_hours"]
    assert any("the name is taken" in m for m in log)


def test_the_prompt_promises_tools_only_when_actions_reached_the_model() -> None:
    business = Settings("Anna's Salon", "Öppet.", ("sv",), (EXAMPLE,))
    assert "You also have tools" not in system_instruction(business)
    assert "You also have tools" in system_instruction(business, has_actions=True)


def test_the_modules_hours_cannot_be_guessed_from_the_test_business() -> None:
    """The paid Scenario proves an Action was used only if its answer is not in the prompt."""

    def closing_times(hours: str) -> set[str]:
        return set(re.findall(r"-(\d+)", hours))

    assert closing_times(HOURS).isdisjoint(closing_times(BUSINESS_FACTS))
    module_business = json.loads(MODULE_BUSINESS_FILE.read_text("utf-8"))
    assert not closing_times(module_business["facts"]), (
        "this Business's facts hold hours"
    )
