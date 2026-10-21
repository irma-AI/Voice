"""A Business's own AI assistant sends Commands to the agent endpoint with an Access token (ADR 0003, make test-db). No mocks of our own code.

The Commands run on the SDK's worker threads with their own database connection, so these tests commit (transaction=True).
"""

# pyright: basic
# (django-stubs types model fields for mypy's plugin; strict pyright cannot read them)

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from asgiref.sync import async_to_sync
from django.conf import settings
from django.db import IntegrityError, connection, transaction
from django.test import Client
from mcp.server.mcpserver import Context
from mcp.types import ToolAnnotations

from portal.accounts import agent, changes, tokens
from portal.accounts.models import (
    AccessToken,
    Account,
    Business,
    CallLog,
    CommandRecord,
    Module,
)
from tests.portal.helpers import EVENTS, PASSWORD, a_call

pytestmark = [pytest.mark.db, pytest.mark.django_db(transaction=True)]


@pytest.fixture(autouse=True)
def operator_named(settings: Any) -> None:
    settings.SUPER_ADMIN_EMAIL = "user-a@example.com"  # a_business()'s, so its operator tokens are the operator's
    settings.CORE_SECRET = "a-secret-for-tests"  # so get_test_call_link signs a ticket


ERAS = [
    "2025-11-25",
    "2026-07-28",
]  # both live (docs/research/mcp-server-framework.md § 2)


def ask(
    method: str,
    params: dict[str, Any] | None = None,
    secret: str | None = None,
    era: str = "2026-07-28",
    **headers: str,
) -> Any:
    """One JSON-RPC request to the agent endpoint, as an MCP client sends it."""
    if secret is not None:
        headers["Authorization"] = f"Bearer {secret}"
    params = dict(params or {})
    if (
        era != "2025-11-25"
    ):  # the 2026 era has no handshake: every request carries its envelope
        params["_meta"] = {
            "io.modelcontextprotocol/protocolVersion": era,
            "io.modelcontextprotocol/clientCapabilities": {},
        }
    return Client().post(
        "/mcp/",
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}),
        content_type="application/json",
        headers={
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": era,
            "Mcp-Method": method,
            **({"Mcp-Name": params["name"]} if "name" in params else {}),
            **headers,
        },
    )


def tool_names(answer: Any) -> list[str]:
    assert answer.status_code == 200, answer.content
    return [t["name"] for t in answer.json()["result"]["tools"]]


def a_business(
    email: str = "user-a@example.com", name: str = "Owner A's Salon"
) -> Business:
    return Business.objects.create(
        account=Account.objects.create_user(email, PASSWORD), name=name
    )


def a_token(business: Business, scope: str = "read", operator: bool = False) -> str:
    return AccessToken.make(business, "Claude Code", scope, operator)[1]


def refused_for_its_token(answer: Any) -> bool:
    """The transport's 401, whose challenge starts a client's Connect flow (VOI-119)."""
    return answer.status_code == 401 and answer["WWW-Authenticate"].startswith("Bearer")


CALL = {"name": "list_recent_calls", "arguments": {}}


@pytest.mark.parametrize("era", ERAS)
def test_an_assistant_with_no_token_sees_the_business_commands(era: str) -> None:
    assert tool_names(ask("tools/list", era=era)) == [
        "list_recent_calls",
        "list_call_logs",
        "read_call_log",
        "remove_module",
        "list_modules",
        "check_module",
        "add_module",
        "get_call_button",
        "get_test_call_link",
        "list_pending_changes",
        "approve_change",
        "reject_change",
        "read_settings",
        "change_settings",
        "change_business_details",
    ]


@pytest.mark.parametrize("era", ERAS)
def test_a_command_with_no_token_a_wrong_one_or_a_revoked_one_gets_a_401(
    era: str,
) -> None:
    business = a_business()
    revoked = a_token(business)
    AccessToken.objects.get().revoke()
    assert refused_for_its_token(ask("tools/call", CALL, era=era))
    for secret in (revoked, "voice_not-a-token", "", "x" * 5000):
        assert refused_for_its_token(ask("tools/call", CALL, secret, era=era))
        assert refused_for_its_token(ask("tools/list", secret=secret, era=era))
    assert not CommandRecord.objects.exists()


def test_a_request_with_no_token_that_cannot_be_read_is_refused() -> None:
    for body in (
        "not json",
        "[]",
        '{"method": 7}',
        '[{"jsonrpc": "2.0", "id": 1, "method": "tools/call"}]',
    ):
        answer = Client().post("/mcp/", body, content_type="application/json")
        assert refused_for_its_token(answer)


# What each kind of token may run, written out here rather than read from the endpoint, so a change there shows up as a failure.
MAY_RUN = {
    "read": {"read"},
    "full": {"read", "write"},
    "operator read": {"read", "operator_read"},
    "operator full": {"read", "write", "operator_read", "operator_write"},
}
LIVE_KINDS = {
    "read": ("read", False),
    "full": ("full", False),
    "operator read": ("read", True),
    "operator full": ("full", True),
}
# Arguments for a Command that needs some; one with required arguments and no entry here fails the sweep below.
EXAMPLE_ARGUMENTS: dict[str, dict[str, Any]] = {
    "remove_module": {"name": "Bookings"},
    "change_settings": {"accent": "#1a2a44"},
    "change_business_details": {"name": "Owner A's Hair"},
    "check_module": {"name": "Bookings"},
    "read_call_log": {"call": "c0ffee-0123456789"},
    "add_module": {"name": "Hours", "address": "https://8.8.4.4/mcp"},
    "invite_business": {"name": "New Salon", "email": "new@example.com"},
}
# What a Command that ran leaves in its Command record: a destructive one only stages its change (VOI-239).
STAGED = {"remove_module", "change_business_details", "invite_business"}


def same_as_no_such_command(name: str, secret: str, era: str = "2026-07-28") -> bool:
    """The whole answer to a refused Command, its name aside, is the SDK's answer to a Command that does not exist."""
    answer = call(name, secret, era).json()["result"]
    nonexistent = call("no_such_command", secret, era).json()["result"]
    assert (
        nonexistent["isError"]
        and nonexistent["content"][0]["text"] == "Unknown tool: no_such_command"
    )
    return json.dumps(answer).replace(name, "no_such_command") == json.dumps(
        nonexistent
    )


def waiting_change(secret: str) -> dict[str, Any]:
    """A fresh harmless change for approve_change and reject_change to decide: Swedish only, as a new Business already is."""
    token = AccessToken.objects.get(token_hash=tokens.hash_of(secret))
    if token.revoked_at is not None or token.scope != "full":
        return {"change": 0}  # refused before it is read
    return {
        "change": changes.stage(token, "change_details", {}, {"languages": ["sv"]})[
            "change"
        ]
    }


def call(name: str, secret: str, era: str = "2026-07-28", **headers: str) -> Any:
    arguments = (
        waiting_change(secret)
        if name in ("approve_change", "reject_change")
        and secret.startswith("voice_")
        and AccessToken.objects.filter(token_hash=tokens.hash_of(secret)).exists()
        else EXAMPLE_ARGUMENTS.get(
            name, {"change": 0} if name in ("approve_change", "reject_change") else {}
        )
    )
    return ask(
        "tools/call",
        {"name": name, "arguments": arguments},
        secret,
        era,
        **headers,
    )


@pytest.mark.parametrize("era", ERAS)
def test_every_command_against_every_kind_of_token(era: str) -> None:
    assert set(agent.COMMANDS.values()) <= set(MAY_RUN["operator full"]), (
        "add the new need to MAY_RUN"
    )
    business = a_business()
    # Not public, so check_module's probe refuses it at once and asks nothing on the internet.
    Module.objects.create(
        business=business, name="Bookings", url="https://127.0.0.1/mcp"
    )
    CallLog.objects.create(  # read_call_log's example
        call_id="c0ffee-0123456789",
        business=business,
        kind="test",
        started_at=datetime(2026, 10, 19, 5, tzinfo=UTC),
        events=EVENTS,
    )
    Business.objects.filter(pk=business.pk).update(website_domain="example.se")
    business.refresh_from_db()  # get_call_button needs a saved website
    for kind, (scope, operator) in LIVE_KINDS.items():
        # What the last kind's add_module added.
        Module.remove(Module.objects.filter(name="Hours"))
        secret = a_token(business, scope, operator)
        listed = tool_names(ask("tools/list", secret=secret, era=era))
        assert listed == [
            n for n, need in agent.COMMANDS.items() if need in MAY_RUN[kind]
        ], kind
        for name, need in agent.COMMANDS.items():
            if need in MAY_RUN[kind]:
                answer = call(name, secret, era).json()["result"]
                assert not answer.get("isError"), (kind, name, answer)
            else:
                assert same_as_no_such_command(name, secret, era), (kind, name)
            newest = CommandRecord.objects.order_by(
                "-id"
            ).first()  # appended to only, so the newest is this call's
            assert (
                newest is not None
                and newest.command == name
                and newest.token.business == business
            )
            ran = "staged" if name in STAGED else "done"
            assert newest.result == (ran if need in MAY_RUN[kind] else "refused"), (
                kind,
                name,
            )
    revoked = a_token(business, "full", True)
    AccessToken.objects.filter(token_hash=tokens.hash_of(revoked)).get().revoke()
    records = CommandRecord.objects.count()
    for secret in (revoked, "voice_unknown"):
        for name in agent.COMMANDS:
            assert refused_for_its_token(call(name, secret, era))
    assert CommandRecord.objects.count() == records


def test_a_command_missing_from_the_table_is_refused_even_for_the_operators_full_token() -> (
    None
):
    @agent.command("Not in the table", ToolAnnotations(read_only_hint=True))
    def not_in_the_table(ctx: Context[Any, Any]) -> str:
        return "ran"

    try:
        secret = a_token(a_business(), "full", operator=True)
        assert "not_in_the_table" not in tool_names(ask("tools/list", secret=secret))
        assert same_as_no_such_command("not_in_the_table", secret)
        assert CommandRecord.objects.get().result == "refused"
    finally:
        agent.server.remove_tool("not_in_the_table")


@pytest.mark.parametrize("need", sorted(MAY_RUN["operator full"]))
def test_a_command_of_each_need_is_listed_and_run_only_for_the_tokens_that_may(
    need: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Today's Commands only read; this checks the gate for every need before a Command of it exists."""

    @agent.command("A Command of one need", ToolAnnotations(read_only_hint=True))
    def one_need(ctx: Context[Any, Any]) -> str:
        return "ran"

    monkeypatch.setitem(agent.COMMANDS, "one_need", need)
    try:
        business = a_business()
        listed_without_token = "one_need" in tool_names(ask("tools/list"))
        assert listed_without_token == (need in ("read", "write"))
        for kind, (scope, operator) in LIVE_KINDS.items():
            secret = a_token(business, scope, operator)
            may = need in MAY_RUN[kind]
            assert (
                "one_need" in tool_names(ask("tools/list", secret=secret))
            ) == may, kind
            if may:
                assert (
                    call("one_need", secret).json()["result"]["content"][0]["text"]
                    == "ran"
                )
            else:
                assert same_as_no_such_command("one_need", secret), kind
    finally:
        agent.server.remove_tool("one_need")


def test_recent_calls_are_the_tokens_own_businesss_newest_first_with_no_cost_or_call_id() -> (
    None
):
    mine, theirs = a_business(), a_business("user-b@example.com", "Owner B's Garage")
    start = datetime(2026, 10, 1, 9, tzinfo=UTC)
    for i in range(22):
        a_call(
            mine,
            f"call-mine-{i:04d}",
            start + timedelta(hours=i),
            kind="test" if i == 21 else "call_link",
        )
    a_call(theirs, "call-theirs-0001", start + timedelta(days=5))
    answer = call("list_recent_calls", a_token(mine)).json()["result"]
    calls = answer["structuredContent"]["result"]
    assert len(calls) == 20  # the newest 20
    assert [c["started_at"] for c in calls] == [
        (start + timedelta(hours=i)).isoformat() for i in range(21, 1, -1)
    ]
    assert calls[0] == {
        "started_at": (start + timedelta(hours=21)).isoformat(),
        "length_seconds": 184,
        "kind": "test",
    }
    assert "call-" not in json.dumps(answer) and "0.0123" not in json.dumps(answer)


def test_a_command_record_is_never_changed_or_deleted() -> None:
    call("list_recent_calls", a_token(a_business()))
    record = CommandRecord.objects.get()
    assert record.result == "done" and record.sent_at is not None
    for statement in (
        "UPDATE accounts_commandrecord SET result = 'refused'",
        "UPDATE accounts_commandrecord SET sent_at = now() - interval '1 day'",
        "DELETE FROM accounts_commandrecord",
    ):
        with (
            pytest.raises(IntegrityError, match="command_record_is_append_only"),
            transaction.atomic(),
            connection.cursor() as cursor,
        ):
            cursor.execute(statement)
    with (
        pytest.raises(IntegrityError, match="command_record_is_append_only"),
        transaction.atomic(),
    ):
        CommandRecord.objects.all().delete()
    assert CommandRecord.objects.get().result == "done"


def test_a_command_record_holds_only_a_known_result_and_a_command_name() -> None:
    a_token(a_business())
    token = AccessToken.objects.get()
    for bad in ({"result": "maybe"}, {"command": "list recent calls; drop"}):
        with pytest.raises(IntegrityError), transaction.atomic():
            CommandRecord.objects.create(
                **{
                    "token": token,
                    "command": "list_recent_calls",
                    "result": "done",
                    **bad,
                }
            )


def test_a_request_past_the_cap_is_refused_at_once_and_runs_no_command() -> None:
    secret = a_token(a_business())
    for _ in range(agent.AT_ONCE):
        assert agent._slots.acquire(blocking=False)  # pyright: ignore[reportPrivateUsage]
    try:
        busy = call("list_recent_calls", secret)
        assert busy.status_code == 503 and busy["Retry-After"] == "1"
        assert not CommandRecord.objects.exists()
    finally:
        for _ in range(agent.AT_ONCE):
            agent._slots.release()  # pyright: ignore[reportPrivateUsage]
    assert call("list_recent_calls", secret).status_code == 200


def test_a_command_past_its_timeout_stops_and_is_recorded_as_timed_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    @agent.command("Slow", ToolAnnotations(read_only_hint=True))
    def slow(ctx: Context[Any, Any]) -> str:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_sleep(5)")
        return "ran"

    monkeypatch.setitem(agent.COMMANDS, "slow", "read")
    monkeypatch.setattr(agent, "COMMAND_TIMEOUT_MS", 100)
    try:
        answer = call("slow", a_token(a_business())).json()["result"]
        assert (
            answer["isError"]
            and answer["content"][0]["text"] == "This took too long. Try again."
        )
        assert CommandRecord.objects.get().result == "timed_out"
    finally:
        agent.server.remove_tool("slow")


def test_a_request_from_another_sites_page_is_refused() -> None:
    secret = a_token(a_business())
    assert (
        call("list_recent_calls", secret, Origin="https://attacker.example").status_code
        == 403
    )
    portal = settings.PORTAL_URL.rstrip("/")
    assert call("list_recent_calls", secret, Origin=portal).status_code == 200


def test_a_token_that_sends_a_command_shows_when_it_was_last_used() -> None:
    secret = a_token(a_business())
    assert AccessToken.objects.get().last_used_at is None
    call("list_recent_calls", secret)
    assert AccessToken.objects.get().last_used_at is not None


def test_the_catalogue_is_closed_byte_stable_and_small() -> None:
    names = [t.name for t in async_to_sync(agent.server.list_tools)()]
    assert sorted(names) == sorted(agent.COMMANDS), (
        "add the Command to COMMANDS, or its entry's Command to agent.py"
    )
    assert set(names) <= agent.GATED, (
        "add every Command with @command: a tool added any other way skips the gate and the record"
    )
    secret = a_token(a_business(), "full", operator=True)
    first, second = ask("tools/list", secret=secret), ask("tools/list", secret=secret)
    assert first.content == second.content  # no per-request value in a definition
    assert len(first.content) <= 16_000, (
        "tools/list is past its ceiling: shorten descriptions or split a Command"
    )
    for tool in first.json()["result"]["tools"]:
        assert tool["inputSchema"].get("additionalProperties") is False, tool["name"]
        assert 0 < len(tool["description"]) <= 280, tool["name"]
        assert tool.get("title") and "readOnlyHint" in tool.get("annotations", {}), (
            tool["name"]
        )


def test_a_token_that_cannot_be_checked_is_refused_with_why(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = a_token(a_business())
    connection.close()
    monkeypatch.setitem(
        connection.settings_dict, "PORT", "1"
    )  # the database stops answering
    try:
        answer = call("list_recent_calls", secret)
        assert (
            answer.status_code == 503
            and b"cannot check Access tokens" in answer.content
        )
    finally:
        connection.close()
    monkeypatch.undo()
    assert not CommandRecord.objects.exists()


def test_a_header_that_names_another_method_than_the_body_is_refused() -> None:
    """The no-token check reads the body's method; the SDK refuses a request whose Mcp-Method header says otherwise."""
    mismatched = {"Mcp-Method": "tools/call", "Mcp-Name": "list_recent_calls"}
    answer = ask("tools/list", **mismatched)  # pyright: ignore[reportArgumentType]
    assert answer.status_code == 400 and "result" not in answer.json()


def test_agents_hold_at_most_half_of_the_portals_threads() -> None:
    """AT_ONCE lives in agent.py and gunicorn's thread count in Dockerfile.portal: when they drift, edit AT_ONCE."""
    threads = re.search(
        r"--threads (\d+)", (settings.BASE_DIR.parent / "Dockerfile.portal").read_text()
    )
    assert threads, "Dockerfile.portal no longer names gunicorn's --threads"
    assert 1 <= agent.AT_ONCE <= int(threads.group(1)) // 2


def test_a_hidden_command_called_with_wrong_arguments_still_answers_like_an_unknown_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The token is checked before the arguments, so their errors never tell a hidden Command exists (skeptic pass, VOI-112)."""

    @agent.command("Takes a number", ToolAnnotations(read_only_hint=True))
    def takes_a_number(ctx: Context[Any, Any], number: int) -> int:
        return number

    monkeypatch.setitem(agent.COMMANDS, "takes_a_number", "operator_read")
    try:
        secret = a_token(a_business())
        for arguments in ({}, {"number": "not a number"}, {"number": 1, "extra": 2}):
            answer = ask(
                "tools/call",
                {"name": "takes_a_number", "arguments": arguments},
                secret,
            ).json()["result"]
            nonexistent = ask(
                "tools/call",
                {"name": "no_such_command", "arguments": arguments},
                secret,
            ).json()["result"]
            assert json.dumps(answer).replace(
                "takes_a_number", "no_such_command"
            ) == json.dumps(nonexistent), arguments
        assert (
            list(CommandRecord.objects.values_list("result", flat=True))
            == ["refused"] * 3
        )
    finally:
        agent.server.remove_tool("takes_a_number")


def test_an_argument_the_schema_does_not_name_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """additionalProperties: false is kept, not only advertised: the SDK alone drops an unknown argument and runs."""
    secret = a_token(a_business())
    answer = ask(
        "tools/call",
        {"name": "list_recent_calls", "arguments": {"business": 1}},
        secret,
    ).json()["result"]
    assert answer["isError"] and "business" in answer["content"][0]["text"]
    assert CommandRecord.objects.get().result == "refused"


def test_a_command_record_takes_the_databases_clock_only() -> None:
    a_token(a_business())
    token = AccessToken.objects.get()
    for forged in ("2026-01-01T00:00:00Z", "2099-01-01T00:00:00Z"):
        with (
            pytest.raises(
                IntegrityError, match="command_record_sent_at_is_the_databases_clock"
            ),
            transaction.atomic(),
        ):
            CommandRecord.objects.create(
                token=token, command="list_recent_calls", result="done", sent_at=forged
            )


def test_a_running_command_does_not_hold_up_another_request_with_the_same_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An assistant lists tools while a Command of its runs (skeptic pass round 2, VOI-112)."""

    @agent.command("Slow read", ToolAnnotations(read_only_hint=True))
    def slow_read(ctx: Context[Any, Any]) -> str:
        with (
            connection.cursor() as cursor
        ):  # each statement under the timeout, the Command as a whole past it
            for _ in range(3):
                cursor.execute("SELECT pg_sleep(0.4)")
        return "ran"

    monkeypatch.setitem(agent.COMMANDS, "slow_read", "read")
    monkeypatch.setattr(agent, "COMMAND_TIMEOUT_MS", 600)
    try:
        secret = a_token(a_business())
        with ThreadPoolExecutor(1) as pool:

            def slow_call() -> Any:
                try:
                    return call("slow_read", secret)
                finally:
                    connection.close()  # the test client leaves its thread's connection open

            running = pool.submit(slow_call)
            time.sleep(0.5)  # the Command holds its token
            listed = ask("tools/list", secret=secret)
            running.result()
        assert listed.status_code == 200, listed.content
    finally:
        agent.server.remove_tool("slow_read")


@pytest.mark.parametrize("era", ERAS)
def test_arguments_that_are_not_an_object_get_the_sdks_refusal_for_every_name(
    era: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A hidden Command answers like an unknown one, and the middleware does not crash (skeptic pass round 2, VOI-112)."""

    @agent.command("Hidden", ToolAnnotations(read_only_hint=True))
    def hidden(ctx: Context[Any, Any]) -> str:
        return "ran"

    monkeypatch.setitem(agent.COMMANDS, "hidden", "operator_write")
    try:
        secret = a_token(a_business())
        for arguments in (5, "ab", [{}], True):
            answers = [
                ask("tools/call", {"name": name, "arguments": arguments}, secret, era)
                for name in ("hidden", "no_such_command", "list_recent_calls")
            ]
            bodies = {
                json.dumps(a.json()).replace(n, "X")
                for a, n in zip(
                    answers,
                    ("hidden", "no_such_command", "list_recent_calls"),
                    strict=True,
                )
            }
            assert len(bodies) == 1 and "error" in answers[0].json(), (
                arguments,
                bodies,
            )
        assert not CommandRecord.objects.exists()
    finally:
        agent.server.remove_tool("hidden")


def test_call_logs_give_the_operator_every_business_and_a_business_its_own_timings_only() -> (
    None
):
    """VOI-161: the Call log Commands. A log holds no words or audio (the database refuses them, migrations 0020 to 0024);
    the answer carries only the contract's timing fields, so a log that one day held words would fail here first."""
    operator, other = a_business(), a_business("user-b@example.com", "Owner B's Bikes")
    started = datetime(2026, 10, 19, 5, tzinfo=UTC)
    for owner, call_id in ((operator, "log-operator-01"), (other, "log-other-00001")):
        CallLog.objects.create(
            call_id=call_id,
            business=owner,
            kind="test",
            started_at=started,
            events=EVENTS,
            words=[
                {"t": 1.0, "who": "caller", "text": "Vad kostar en klippning?"}
            ],  # VOI-160
        )
    timing_fields = set(
        json.loads(
            (Path(__file__).parents[2] / "contract/call-log.schema.json").read_text()
        )["$defs"]["event"]["properties"]
    )

    def answer(secret: str, name: str, **arguments: Any) -> Any:
        return ask("tools/call", {"name": name, "arguments": arguments}, secret).json()[
            "result"
        ]

    as_operator = a_token(operator, "read", operator=True)
    listed = answer(as_operator, "list_call_logs")["structuredContent"]["result"]
    assert {log["call"] for log in listed} == {"log-operator-01", "log-other-00001"}
    assert listed[0]["barge_ins"] == 1
    read = answer(as_operator, "read_call_log", call="log-other-00001")
    assert read["structuredContent"]["events"] == EVENTS
    assert "klippning" not in json.dumps(
        read
    )  # a test call's words stay on the operator's page
    assert {
        key for event in read["structuredContent"]["events"] for key in event
    } <= timing_fields

    as_other = a_token(other, "full")
    assert [
        log["call"]
        for log in answer(as_other, "list_call_logs")["structuredContent"]["result"]
    ] == ["log-other-00001"]
    assert answer(as_other, "read_call_log", call="log-operator-01")["isError"]
    assert CommandRecord.objects.filter(command="read_call_log").count() == 2
