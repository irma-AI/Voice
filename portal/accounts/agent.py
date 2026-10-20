# pyright: basic
# (django-stubs types model fields for mypy's plugin; strict pyright cannot read them)
"""The agent endpoint (ADR 0003): one MCP endpoint where a Business's own AI assistant sends Commands with an Access token.

Every Command lives here, so a move to another framework or host only relocates this module. The official SDK (`mcp`)
serves it, and `django-stateless-mcp` (pinned) runs the SDK inside a Django view under gunicorn.
"""

import functools
import json
import threading
from collections.abc import Callable
from typing import Any, Literal, assert_never

from asgiref.sync import async_to_sync
from django.conf import settings
from django.db import DatabaseError, OperationalError, connection, transaction
from django.db.models.functions import Now
from django.http import HttpRequest, HttpResponse, HttpResponseBase
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django_stateless_mcp import django_request, mcp_view
from mcp.server.context import CallNext, HandlerResult, ServerRequestContext
from mcp.server.mcpserver import Context, MCPServer
from mcp.types import CallToolResult, TextContent, ToolAnnotations
from psycopg.errors import QueryCanceled

from portal.accounts import tokens
from portal.accounts.models import AccessToken, CallRecord, CommandRecord

# What a Command needs from the token that sends it. An operator Command is split by read and write like a Business's,
# so the operator's read-only token runs no operator write.
Need = Literal["read", "write", "operator_read", "operator_write"]

# Deny by default: every Command has an entry, and a Command with no entry is refused even with a full operator token.
COMMANDS: dict[str, Need] = {"list_recent_calls": "read"}

# Each database statement of a Command stops after this (Postgres statement_timeout), so a stuck one gives its thread back.
# shortcut: only each statement is timed, not the Command (a thread cannot be stopped); add a deadline of its own before a Command makes several slow queries or calls out to the network.
COMMAND_TIMEOUT_MS = 5000

# Requests served at once. gunicorn has 4 threads (Dockerfile.portal) and the core asks the Portal for settings at every
# call start, so agents never hold more than half of them; the rest get a 503 at once (DECISIONS.md, VOI-112).
AT_ONCE = 2
_slots = threading.BoundedSemaphore(AT_ONCE)

# What a client may send before it has a token: the handshake (2025 era), discovery (2026 era) and the tool list.
# Anything else, a tools/call above all, gets the 401 whose challenge starts the client's Connect flow (VOI-119).
WITHOUT_TOKEN = {
    "initialize",
    "notifications/initialized",
    "server/discover",
    "ping",
    "tools/list",
}


def may_use(token: AccessToken | None, need: Need | None) -> bool:
    """Whether a token may run a Command; None is no token, which may only see a Business's Commands listed."""
    if token is None or need is None:
        return False
    full = token.scope == "full"
    match need:
        case "read":
            return True
        case "write":
            return full
        case "operator_read":
            return token.is_operator
        case "operator_write":
            return token.is_operator and full
        case _:
            assert_never(need)


def may_see(token: AccessToken | None, name: str) -> bool:
    need = COMMANDS.get(name)
    if token is None:
        return (
            need in ("read", "write")
        )  # an assistant not yet connected sees what a Business can do, never the operator's
    return may_use(token, need)


def caller(ctx: Context[Any, Any]) -> AccessToken | None:
    return getattr(django_request(ctx), "agent_token", None)


def failed(text: str) -> CallToolResult:
    return CallToolResult(content=[TextContent(type="text", text=text)], is_error=True)


def refused(name: str) -> CallToolResult:
    """The SDK's own answer to a tool that does not exist, so a refusal does not tell a hidden Command exists."""
    return failed(f"Unknown tool: {name}")


async def list_follows_the_token(
    ctx: ServerRequestContext[Any, Any], call_next: CallNext
) -> HandlerResult:
    """Hides from tools/list what the token may not run. Hiding is not the gate: every Command checks again (`command`)."""
    result = await call_next(ctx)
    if ctx.method != "tools/list" or result is None:
        return result
    request = getattr(getattr(ctx.request, "state", None), "django_request", None)
    token = getattr(request, "agent_token", None)
    tools = result["tools"] if isinstance(result, dict) else result.tools  # pyright: ignore[reportAttributeAccessIssue]
    kept = [
        t for t in tools if may_see(token, t["name"] if isinstance(t, dict) else t.name)
    ]
    if isinstance(result, dict):
        result["tools"] = kept
    else:
        result.tools = kept  # pyright: ignore[reportAttributeAccessIssue]
    return result


server = MCPServer("Voice", middleware=[list_follows_the_token])

# The Commands `command` added, so a test can tell one added any other way (it would skip the gate and the record).
GATED: set[str] = set()


def command(
    title: str, annotations: ToolAnnotations
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """The one way a Command is added: it checks its own token, runs under the timeout and leaves a Command record."""

    def add(fn: Callable[..., Any]) -> Callable[..., Any]:
        name = fn.__name__

        @functools.wraps(fn)
        def gated(ctx: Context[Any, Any], **arguments: Any) -> Any:
            try:
                return run(caller(ctx), ctx, arguments)
            finally:
                connection.close()  # the SDK's worker thread keeps no connection of its own between Commands

        def run(
            token: AccessToken | None, ctx: Context[Any, Any], arguments: dict[str, Any]
        ) -> Any:
            if (
                token is None
            ):  # the endpoint answers a tools/call with no token with a 401; this is the second lock
                return refused(name)
            if not may_use(token, COMMANDS.get(name)):
                CommandRecord.objects.create(
                    token=token, command=name, result="refused"
                )
                return refused(name)
            try:
                with transaction.atomic():
                    with connection.cursor() as cursor:
                        cursor.execute(
                            "SELECT set_config('statement_timeout', %s, true)",
                            [str(COMMAND_TIMEOUT_MS)],
                        )
                    result = fn(ctx, **arguments)
            except OperationalError as error:
                timed_out = isinstance(error.__cause__, QueryCanceled)
                CommandRecord.objects.create(
                    token=token,
                    command=name,
                    result="timed_out" if timed_out else "failed",
                )
                if timed_out:
                    return failed("This took too long. Try again.")
                raise
            except BaseException:
                CommandRecord.objects.create(token=token, command=name, result="failed")
                raise
            CommandRecord.objects.create(token=token, command=name, result="done")
            return result

        server.add_tool(gated, title=title, annotations=annotations)
        GATED.add(name)
        server._tool_manager.get_tool(name).parameters["additionalProperties"] = False  # pyright: ignore[reportPrivateUsage, reportOptionalMemberAccess]
        return gated

    return add


@command("Recent calls", ToolAnnotations(read_only_hint=True))
def list_recent_calls(ctx: Context[Any, Any]) -> list[dict[str, Any]]:
    """Your Business's 20 most recent calls, newest first: when each started (UTC), how long it lasted in seconds, and whether it was a test call or came through the Call link."""
    token = caller(ctx)
    assert token is not None  # `command` refused it otherwise
    return [
        {
            "started_at": r.started_at.isoformat(),
            "length_seconds": r.length_seconds,
            "kind": r.kind,
        }
        for r in CallRecord.objects.filter(business=token.business).order_by(
            "-started_at"
        )[:20]
    ]


served = mcp_view(server)


def challenge(description: str) -> HttpResponse:
    """The transport's 401: a client reads `WWW-Authenticate` and asks its person to connect again."""
    answer = HttpResponse(
        json.dumps({"error": "invalid_token", "error_description": description}),
        status=401,
        content_type="application/json",
    )
    answer["WWW-Authenticate"] = (
        f'Bearer error="invalid_token", error_description="{description}"'
    )
    return answer


def live_token(header: str) -> AccessToken | None:
    scheme, _, secret = header.partition(" ")
    if scheme.lower() != "bearer" or not secret.startswith(tokens.PREFIX):
        return None
    token = (
        AccessToken.objects.filter(
            token_hash=tokens.hash_of(secret), revoked_at__isnull=True
        )
        .select_related("business")
        .first()
    )
    if token is not None:
        AccessToken.objects.filter(pk=token.pk).update(last_used_at=Now())
    return token


def asks_without_token(body: bytes) -> bool:
    """Only a single readable message whose method is in WITHOUT_TOKEN; anything else is refused (fail closed)."""
    try:
        message = json.loads(body)
    except ValueError:
        return False
    return isinstance(message, dict) and message.get("method") in WITHOUT_TOKEN


@csrf_exempt  # a bearer token gates it, never a cookie
@never_cache
def endpoint(request: HttpRequest) -> HttpResponseBase:
    """The agent endpoint: a Business's Commands over MCP, at most AT_ONCE requests at a time."""
    origin = request.headers.get("Origin")
    if origin is not None and origin != settings.PORTAL_URL.rstrip("/"):
        return HttpResponse(
            "This origin may not call the agent endpoint.", status=403
        )  # the spec's DNS-rebinding rule
    if not _slots.acquire(blocking=False):
        busy = HttpResponse("Too many requests at once. Try again shortly.", status=503)
        busy["Retry-After"] = "1"
        return busy
    try:
        header = request.headers.get("Authorization")
        if header is None:
            token = None
            if not asks_without_token(request.body):
                return challenge("Connect with an Access token from the Portal")
        else:
            try:
                token = live_token(header)
            except DatabaseError:
                unchecked = HttpResponse(
                    "The Portal cannot check Access tokens right now. Try again shortly.",
                    status=503,
                )
                unchecked["Retry-After"] = "5"
                return unchecked
            if token is None:
                return challenge("This Access token is wrong or revoked")
        request.agent_token = token  # pyright: ignore[reportAttributeAccessIssue]
        return async_to_sync(served)(request)
    finally:
        _slots.release()
