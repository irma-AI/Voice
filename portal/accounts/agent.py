# pyright: basic
# (django-stubs types model fields for mypy's plugin; strict pyright cannot read them)
"""The agent endpoint (ADR 0003): one MCP endpoint where a Business's own AI assistant sends Commands with an Access token.

Every Command lives here, so a move to another framework or host only relocates this module. The official SDK (`mcp`)
serves it, and `django-stateless-mcp` (pinned) runs the SDK inside a Django view under gunicorn.
"""

import base64
import binascii
import contextlib
import functools
import json
import threading
from collections.abc import Callable, Iterator
from dataclasses import replace
from typing import Any, Literal, assert_never

from asgiref.sync import async_to_sync, sync_to_async
from django.conf import settings
from django.db import DatabaseError, OperationalError, connection, transaction
from django.db.models.functions import Now
from django.http import HttpRequest, HttpResponse, HttpResponseBase
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django_stateless_mcp import django_request, mcp_view
from mcp.server.context import CallNext, HandlerResult, ServerRequestContext
from mcp.server.mcpserver import Context, MCPServer
from mcp.types import CallToolResult, TextContent, ToolAnnotations
from psycopg.errors import QueryCanceled

from portal.accounts import changes, tokens
from portal.accounts.domain import shown_domain
from portal.accounts.models import (
    AccessToken,
    Business,
    CallRecord,
    CommandRecord,
    Module,
)
from portal.accounts.settings_form import changed, problems

# What a Command needs from the token that sends it. An operator Command is split by read and write like a Business's,
# so the operator's read-only token runs no operator write.
Need = Literal["read", "write", "operator_read", "operator_write"]

# Deny by default: every Command has an entry, and a Command with no entry is refused even with a full operator token.
COMMANDS: dict[str, Need] = {
    "list_recent_calls": "read",
    "remove_module": "write",
    "read_settings": "read",
    "change_settings": "write",
    "change_business_details": "write",
}

# Each database statement of a Command stops after this (Postgres statement_timeout), so a stuck one gives its thread back.
# shortcut: only each statement is timed, not the Command (a thread cannot be stopped); add a deadline of its own before a Command makes several slow queries or calls out to the network.
COMMAND_TIMEOUT_MS = 5000

# Requests served at once. gunicorn has 4 threads (Dockerfile.portal) and the core asks the Portal for settings at every
# call start, so requests the endpoint is serving never hold more than half of them; the rest get a 503 at once
# (DECISIONS.md, VOI-112). A client that sends its body slowly holds a thread before any view runs: not bounded here.
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


def as_answer(staged: dict[str, Any]) -> CallToolResult:
    """A staged change's answer, as data and as text, so no agent infers from prose that it is done."""
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(staged))],
        structured_content=staged,
    )


def refused(name: str) -> CallToolResult:
    """The SDK's own answer to a tool that does not exist, so a refusal does not tell a hidden Command exists."""
    return failed(f"Unknown tool: {name}")


# No Command can have this name (COMMAND_NAME_PATTERN has no hyphen), so the SDK answers it as unknown.
NO_COMMAND = "no-command"


async def sdk_answer(
    ctx: ServerRequestContext[Any, Any], call_next: CallNext, text: str
) -> HandlerResult:
    """The SDK's own error answer with its envelope for the request's era (a middleware that answers alone owns the
    envelope, the SDK's docs say), carrying `text`: the SDK answers a Command that cannot exist, and the text is swapped."""
    params = {**(ctx.params or {}), "name": NO_COMMAND, "arguments": {}}
    answer = await call_next(replace(ctx, params=params))
    assert (
        isinstance(answer, dict)
        and answer["content"][0]["text"] == f"Unknown tool: {NO_COMMAND}"
    )
    answer["content"][0]["text"] = text
    return answer


def refuse(token: AccessToken, name: str) -> None:
    CommandRecord.objects.create(token=token, command=name, result="refused")


async def follows_the_token(
    ctx: ServerRequestContext[Any, Any], call_next: CallNext
) -> HandlerResult:
    """Hides from tools/list what the token may not run, and refuses a tools/call before the SDK reads its arguments, so
    their errors never tell a hidden Command exists. Neither is the only gate: every Command checks again (`command`)."""
    request = getattr(getattr(ctx.request, "state", None), "django_request", None)
    token = getattr(request, "agent_token", None)
    if ctx.method == "tools/call":
        params = ctx.params or {}
        name = params.get("name")
        arguments = params.get("arguments")
        # Arguments that are not an object go on untouched: the SDK refuses them alike for every name.
        readable = arguments is None or isinstance(arguments, dict)
        need = COMMANDS.get(name) if isinstance(name, str) and readable else None
        if (
            need is not None
        ):  # a name with no entry goes on, to the SDK's "Unknown tool" or the Command's own refusal
            assert isinstance(name, str)
            if token is None:
                return await sdk_answer(ctx, call_next, f"Unknown tool: {name}")
            if not may_use(token, need):
                await sync_to_async(refuse)(token, name)
                return await sdk_answer(ctx, call_next, f"Unknown tool: {name}")
            tool = server._tool_manager.get_tool(name)  # pyright: ignore[reportPrivateUsage]
            named = set(tool.parameters.get("properties", {})) if tool else set()
            extra = sorted(set(arguments or {}) - named)
            if extra:  # the SDK would drop it and run; the schema says additionalProperties: false
                await sync_to_async(refuse)(token, name)
                return await sdk_answer(
                    ctx, call_next, f"{name} takes no argument named {extra[0]}."
                )
    result = await call_next(ctx)
    if ctx.method != "tools/list" or result is None:
        return result
    tools = result["tools"] if isinstance(result, dict) else result.tools  # pyright: ignore[reportAttributeAccessIssue]
    kept = [
        t for t in tools if may_see(token, t["name"] if isinstance(t, dict) else t.name)
    ]
    if isinstance(result, dict):
        result["tools"] = kept
    else:
        result.tools = kept  # pyright: ignore[reportAttributeAccessIssue]
    return result


server = MCPServer("Voice", middleware=[follows_the_token])


@contextlib.contextmanager
def timed() -> Iterator[None]:
    """A transaction whose every statement stops after COMMAND_TIMEOUT_MS, lock waits included."""
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT set_config('statement_timeout', %s, true)",
                [str(COMMAND_TIMEOUT_MS)],
            )
        yield


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
                refuse(token, name)
                return refused(name)
            try:
                with timed():
                    # Revoked since the endpoint read it? No lock: one would hold up the token's other requests (DECISIONS.md).
                    live = AccessToken.objects.filter(
                        pk=token.pk, revoked_at__isnull=True
                    ).first()
                    if live is not None:
                        result = fn(ctx, **arguments)
                        staged = (
                            isinstance(result, CallToolResult)
                            and (result.structured_content or {}).get("staged") is True
                        )
                        # In the Command's transaction: a Command whose record cannot be written does not happen.
                        CommandRecord.objects.create(
                            token=token,
                            command=name,
                            result="staged" if staged else "done",
                        )
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
            if live is None:
                refuse(token, name)
                return refused(name)
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


@command(
    "Remove a Module", ToolAnnotations(read_only_hint=False, destructive_hint=True)
)
def remove_module(ctx: Context[Any, Any], name: str) -> CallToolResult:
    """Asks to remove one of your Business's Modules, by its name. Nothing changes until the Business approves it in the Portal: the answer has staged: true, a preview, the risk level and what to do next."""
    token = caller(ctx)
    assert token is not None  # `command` refused it otherwise
    module = Module.objects.filter(business=token.business, name=name).first()
    if module is None:
        return failed("Your Business has no Module by that name.")
    return as_answer(changes.stage(token, "remove_module", {"module": module.pk}))


def locked(token: AccessToken) -> Business:
    """The token's Business as stored now, locked until the Command commits: the form writes every setting, so none read earlier is written back."""
    return Business.objects.select_for_update().get(pk=token.business.pk)


def settings_of(business: Business) -> dict[str, Any]:
    """The settings as the settings page shows them, named as the Commands name them."""
    return {
        "name": business.name,
        "instructions": business.instructions,
        "languages": business.languages,
        "website": shown_domain(business.website_domain),
        "privacy_notice": business.privacy_url,
        "accent": business.accent,
        "logo": settings.PORTAL_URL.rstrip("/")
        + reverse("logo", args=[business.logo_key])
        if business.logo is not None
        else None,
    }


@command("Read settings", ToolAnnotations(read_only_hint=True))
def read_settings(ctx: Context[Any, Any]) -> dict[str, Any]:
    """Your Business's settings: its name, the instructions the agent follows, the languages it speaks, your website, your privacy notice, and the Theme (accent colour, logo address) your Callers see."""
    token = caller(ctx)
    assert token is not None  # `command` refused it otherwise
    return settings_of(token.business)


@command(
    "Change website, privacy notice and Theme",
    ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=True),
)
def change_settings(
    ctx: Context[Any, Any],
    website: str | None = None,
    privacy_notice: str | None = None,
    accent: str | None = None,
    logo: str | None = None,
    remove_logo: bool = False,
) -> CallToolResult:
    """Changes what you name, at once, by the Portal settings page's rules: website, privacy notice (https), accent ("" for none), logo (base64 PNG, WebP or JPEG, at most 256 KB). Answers with the settings as they now are."""
    token = caller(ctx)
    assert token is not None  # `command` refused it otherwise
    fields: dict[str, Any] = {}
    if website is not None:
        fields["website_domain"] = website
    if privacy_notice is not None:
        fields["privacy_url"] = privacy_notice
    if accent is not None:
        fields.update(use_accent="on" if accent else "", accent=accent)
    if remove_logo:
        fields["remove_logo"] = "on"
    business = locked(token)
    try:
        upload = None if logo is None else base64.b64decode(logo, validate=True)
    except binascii.Error:
        return failed("That logo is not base64. Send the image's bytes as base64.")
    form = changed(business, logo=upload, **fields)
    if not form.is_valid():
        return failed(problems(form))
    return as_answer(settings_of(form.save()))


@command(
    "Change the name, instructions or languages",
    ToolAnnotations(read_only_hint=False, destructive_hint=True),
)
def change_business_details(
    ctx: Context[Any, Any],
    name: str | None = None,
    instructions: str | None = None,
    languages: list[str] | None = None,
) -> CallToolResult:
    """Asks to change your Business's name, instructions or languages (sv, en). Nothing changes until the Business approves it in the Portal: the answer has staged: true, a preview, the risk level and what to do next."""
    token = caller(ctx)
    assert token is not None  # `command` refused it otherwise
    given: dict[str, Any] = {
        k: v
        for k, v in (
            ("name", name),
            ("instructions", instructions),
            ("languages", languages),
        )
        if v is not None
    }
    if not given:
        return failed("Name at least one of name, instructions or languages.")
    form = changed(locked(token), **given)
    if not form.is_valid():
        return failed(problems(form))
    values = {k: form.cleaned_data[k] for k in given}
    return as_answer(changes.stage(token, "change_details", {}, values))


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
    with timed():
        return looked_up(secret)


def looked_up(secret: str) -> AccessToken | None:
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
