# Which framework exposes the Portal's actions as MCP tools

Written 2026-10-18. Every page and package page below was read 2026-10-18. This is research, not a decision. Question from `PRODUCT.md`: "Every action a Business can take in the Portal or the core is also to be exposed to that Business as an MCP tool, so their own agents can run Voice as fully as a person in the Portal can." Here Voice is the MCP **server** and the Business's own agent (Claude, ChatGPT, a script) is the client. Pipecat's MCP client for Modules (ADR 0001) is the other direction and is not covered.

Short answer: use the official MCP Python SDK (`mcp`, class `MCPServer`), already in `uv.lock`, behind a Django view in the existing Portal process, with a per-Business bearer token first and OAuth later. FastMCP is the runner-up. Strands cannot serve MCP. Details and the trade-offs are in the Recommendation.

## 1. What this repo already runs

Read from the repo, 2026-10-18.

- Portal: Django 6.1.2 (`uv.lock`), Python 3.13, run by **gunicorn on WSGI**, `--workers 1 --threads 4 --no-control-socket` (`Dockerfile.portal`); there is no `portal/asgi.py`, only `portal/wsgi.py`. One worker because the login limit counts in the worker's memory.
- Core: FastAPI plus uvicorn (`voice/serve.py`, `python -m voice.serve`), its own image, no database, asks the Portal for settings (ADR 0002).
- `mcp` is **2.3.0** in the lockfile. Pipecat 1.12.0 requires `mcp[cli]<3,>=2.1.1` ([PyPI JSON](https://pypi.org/pypi/pipecat-ai/1.12.0/json)); the Portal group lists `mcp` unpinned (the Module probe, `portal/accounts/probe.py`, uses its client). Starlette 1.7.0, sse-starlette 3.5.0, pyjwt 2.15.1 are already locked (pulled by `mcp`).
- The Portal's only JSON API today is two shared-secret endpoints for the core (`/api/settings/<id>/`, `/api/calls/`); it has no OpenAPI document.

## 2. The protocol, current revision

Current revision is **2026-07-28** ([Versioning](https://modelcontextprotocol.io/specification/versioning), read 2026-10-18); `/specification/latest` redirects to it.

**Transport.** One MCP endpoint that accepts POST; every JSON-RPC message is its own POST; the reply is one JSON object or a request-scoped SSE stream. This revision removes protocol-level sessions (`Mcp-Session-Id`) and the standalone GET stream, adds `MCP-Protocol-Version`, `Mcp-Method` and `Mcp-Name` request headers, and says servers MUST validate `Origin` (403 if present and invalid) and SHOULD authenticate all connections ([Streamable HTTP](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http), read 2026-10-18). Earlier revisions (`2025-11-25` and before) used an `initialize` handshake and sessions. Both eras are live: Claude Code has a v1 runtime (TypeScript SDK 1.x, handshake) and a v2 runtime (adds 2026-07-28), picked per session ([Claude Code MCP](https://code.claude.com/docs/en/mcp.md), "MCP client runtimes", read 2026-10-18). A server therefore has to answer both eras.

**Authorization** ([spec](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization), read 2026-10-18).
- It is "**OPTIONAL**". If an HTTP server supports it, it SHOULD follow the spec. STDIO servers SHOULD NOT; they take credentials from the environment.
- A protected MCP server is an OAuth 2.1 resource server. It MUST implement Protected Resource Metadata (RFC 9728); clients MUST use it to find the authorization server. The authorization server must offer RFC 8414 or OpenID discovery.
- Client registration, in the client's priority order: pre-registered, then Client ID Metadata Documents (CIMD; SHOULD be supported), then Dynamic Client Registration (DCR; MAY, "deprecated and retained for backwards compatibility"), then ask the user ([registration](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization/client-registration), read 2026-10-18).
- Clients MUST send PKCE and the RFC 8707 `resource` parameter; servers MUST validate that a token was issued for them (audience), MUST answer an invalid or expired token with 401, and MUST NOT accept tokens meant for another resource. `Authorization: Bearer` goes on every request; never in the query string.
- How a client gets a token: unauthenticated request, 401 with `WWW-Authenticate: Bearer resource_metadata="..."`, fetch the metadata, find the authorization server, register (CIMD, DCR or pre-registered), browser authorization-code flow with PKCE, token, retry.

**Minimum for a per-Business bearer token.** The spec has no static-token mode: a long-lived bearer secret is outside the OAuth flow above but is not forbidden (authorization is optional). The server needs only: verify `Authorization: Bearer` on every POST, answer 401 otherwise, never accept it in the URL, and tell the token's Business and scope apart. **Minimum for full OAuth** the Portal also needs: the two `.well-known` documents (resource metadata, authorization-server metadata), `authorize` and `token` endpoints (PKCE S256, form-encoded token requests, refresh tokens), CIMD and/or DCR, audience-bound tokens, and a consent page. The SDK says its own embedded authorization server (`auth_server_provider=`) "predates the AS/RS separation ... New servers should not reach for it" ([Authorization](https://py.sdk.modelcontextprotocol.io/run/authorization/), read 2026-10-18); FastMCP calls writing your own server "an extremely advanced pattern that most users should avoid" ([Full OAuth Server](https://gofastmcp.com/servers/auth/full-oauth-server.md), read 2026-10-18). For Django the usual building block is django-oauth-toolkit plus a DCR add-on, which django-mcp-server's README names ([README](https://raw.githubusercontent.com/gts360/django-mcp-server/main/README.md), read 2026-10-18); I did not evaluate either (not checked).

**What the clients accept.**

| Client | Static bearer / header | OAuth |
|---|---|---|
| Claude Code | Yes: `claude mcp add --transport http <name> <url> --header "Authorization: Bearer ..."`. A rejected configured header is reported as a failed connection and does not fall back to OAuth ([Claude Code MCP](https://code.claude.com/docs/en/mcp.md), read 2026-10-18) | Yes (`/mcp`, `claude mcp login`); CIMD or DCR; loopback redirect on any port |
| claude.ai, Desktop, mobile | **Beta, "available to a limited set of organizations"**: a "Request headers" field in the custom-connector dialog, entered by an organization Owner; one shared credential for the whole organization ([Authenticate with request headers](https://claude.com/docs/connectors/custom/add-unlisted), [Authentication for connectors](https://claude.com/docs/connectors/building/authentication.md), read 2026-10-18) | Yes, default: Anthropic-hosted CIMD, DCR, or your own client id; redirect `https://claude.ai/api/mcp/auth_callback`; needs 401 plus `resource_metadata`; first entry of `authorization_servers` only; discovery and token endpoints must answer in 10 s |
| ChatGPT | **No.** "ChatGPT does not support machine-to-machine OAuth grants ..., nor can it present custom API keys or customer-provided mTLS certificates" ([Authentication](https://developers.openai.com/plugins/build/auth.md), read 2026-10-18). Options are OAuth or no authentication | Yes; CIMD preferred, DCR supported; authorization server must advertise PKCE S256 |
| Any script on the SDK or an API client | Yes (it sets its own headers). Anthropic API's MCP connector: not checked | Library-dependent |

Claude's docs say its OAuth client follows the 2025-03-26, 2025-06-18 and 2025-11-25 authorization specs ([Build an MCP server for Claude](https://claude.com/docs/connectors/building/index.md), read 2026-10-18). Whether claude.ai speaks the 2026-07-28 transport today: not stated on any page I read (not checked).

## 3. The candidates

| | Official SDK `mcp` | FastMCP | Strands Agents | django-stateless-mcp |
|---|---|---|---|---|
| Current | 2.3.0 (2026-10-02); 1.30.0 (2026-09-07) on the old line | 4.1.1 (2026-10-18); 3.4.9 (2026-10-16); last 2.x 2.14.7 (2026-04-13) | 1.61.1 (2026-10-15) | 0.1.11 (2026-08-31); first release 2026-07-29 |
| License | MIT | Apache-2.0 | Apache-2.0 | MIT |
| Serves MCP? | Yes | Yes | **No** | Yes (wraps the SDK) |
| In `uv.lock`? | **Yes, 2.3.0** | No (adds a dependency tree) | No | No |

PyPI JSON, read 2026-10-18: [mcp](https://pypi.org/pypi/mcp/json), [fastmcp](https://pypi.org/pypi/fastmcp/json), [fastmcp-slim](https://pypi.org/pypi/fastmcp-slim/json), [strands-agents](https://pypi.org/pypi/strands-agents/json), [django-stateless-mcp](https://pypi.org/pypi/django-stateless-mcp/json).

### 3.1 Official MCP Python SDK (`mcp` 2.x)

- Docs at [py.sdk.modelcontextprotocol.io](https://py.sdk.modelcontextprotocol.io/) (read 2026-10-18). v2 renamed `FastMCP` to `MCPServer` ("the old import path is gone rather than deprecated"; [What's new](https://py.sdk.modelcontextprotocol.io/whats-new/)). I confirmed in the 2.3.0 wheel that `mcp/server/fastmcp.py` only raises `ModuleNotFoundError` pointing at the migration guide.
- Serving: `mcp.streamable_http_app()` returns a Starlette ASGI app; mount it with `Mount(...)` and enter `mcp.session_manager.run()` in the **host app's** lifespan, because a mounted sub-app's lifespan never runs ([Add to an existing app](https://py.sdk.modelcontextprotocol.io/run/asgi/)). Behind a real hostname every request is 421/403 until `transport_security=TransportSecuritySettings(allowed_hosts=..., allowed_origins=...)` is set ([Deploy & scale](https://py.sdk.modelcontextprotocol.io/run/deploy/)).
- Stateless: on 2026-07-28 there is no session and nothing to be sticky on; `stateless_http=True` only matters for 2025-era clients ([Deploy & scale](https://py.sdk.modelcontextprotocol.io/run/deploy/)). Both eras are always served from one app ([Serving legacy clients](https://py.sdk.modelcontextprotocol.io/run/legacy-clients/)).
- Auth: the server is a resource server. `token_verifier=` (one async method, `verify_token(token) -> AccessToken | None`) plus `auth=AuthSettings(issuer_url, resource_server_url, required_scopes, validate_token_resource)` which publishes RFC 9728 metadata and sends the 401 with `resource_metadata`. `get_access_token()` returns the caller inside any handler. The verifier is the whole integration surface, so a static per-Business token today and OAuth later change the verifier and the well-known routes, not the tools ([Authorization](https://py.sdk.modelcontextprotocol.io/run/authorization/)).
- Tools: `@mcp.tool(title=..., annotations=ToolAnnotations(...))`; sync tools run on a worker thread. Tests: `Client(mcp)` in memory (skips HTTP, so skips auth); `Client("http://...")` over HTTP ([Testing](https://py.sdk.modelcontextprotocol.io/get-started/testing/)).
- Middleware `(ctx, call_next)` over decoded MCP messages exists but is "marked provisional ... may change in a 2.x minor release" ([Middleware](https://py.sdk.modelcontextprotocol.io/advanced/middleware/)).
- v2 breaking changes that bite: tool arguments are no longer validated against the schema before the handler runs ("advertised but never applied"), unexpected exceptions become a sanitized `-32603`, server-initiated requests (sampling, push elicitation) are gone on 2026 connections ([What's new](https://py.sdk.modelcontextprotocol.io/whats-new/)).
- Nothing in the docs mounts it in Django (WSGI or ASGI). Django's own page says to wrap `application` in ASGI middleware or embed Django inside another ASGI app ([Django ASGI](https://docs.djangoproject.com/en/6.1/howto/deployment/asgi/), read 2026-10-18).

### 3.2 FastMCP (gofastmcp.com, Prefect)

- **v4 is the stable line**, built on SDK v2 (`mcp>=2.0,<3`); `fastmcp` is a thin wrapper over `fastmcp-slim` ([Upgrading from FastMCP 3](https://gofastmcp.com/getting-started/upgrading/from-fastmcp-3.md)). v3 is a maintenance line (3.4.9, 2026-10-16); v2 had its last release 2026-04-13. 21 v4 releases in three months (4.0.0a1 2026-07-21, 4.1.1 today); the project says to pin an exact version ([Releases](https://gofastmcp.com/development/releases.md)). The upgrade guide and FAQ call out silent behaviour changes (`httpx2` exceptions, middleware `on_initialize` never runs on the modern protocol; [FAQ](https://gofastmcp.com/more/faq.md)).
- Serves both eras from one URL ([FAQ](https://gofastmcp.com/more/faq.md)).
- Mounting: `mcp.http_app(path=...)` is an ASGI app; mount in Starlette or FastAPI and pass `lifespan=mcp_app.lifespan` ("nested lifespans are not recognized"); an OAuth-protected server mounted under a prefix needs the `.well-known` routes mounted at the root by hand ([HTTP Deployment](https://gofastmcp.com/deployment/http.md)). Stateless: `http_app(stateless_http=True)` or `FASTMCP_STATELESS_HTTP=true`.
- Auth providers: `JWTVerifier` (JWKS), `StaticTokenVerifier` ("should never be used in production"), `DebugTokenVerifier`, `RemoteAuthProvider` for identity providers with DCR, OAuth and OIDC proxies for those without, and many named providers (Auth0, WorkOS, Google, GitHub, Keycloak, Supabase ...) ([Authentication](https://gofastmcp.com/servers/auth/authentication.md), [Token verification](https://gofastmcp.com/servers/auth/token-verification.md)). A custom `TokenVerifier` subclass for a database lookup is possible (inferred from the class layout; not run). Default is `auth=None`, i.e. open.
- Per-component `auth=` checks and `AuthMiddleware` (section 4), middleware, dependency injection, `Client(mcp)` in-memory testing ([Testing](https://gofastmcp.com/servers/testing.md)).
- OpenAPI and FastAPI: `FastMCP.from_fastapi(app)` and `from_openapi(...)` generate tools from a spec. FastMCP's own page says LLMs "achieve significantly better performance with well-designed and curated MCP servers than with auto-converted OpenAPI servers" and to use it "for bootstrapping and prototyping, not for mirroring your API" ([FastAPI](https://gofastmcp.com/integrations/fastapi.md)). The Portal has no OpenAPI document, so this would not apply.
- No Django integration page. Hosting it in the Portal means moving the Portal from gunicorn/WSGI to an ASGI server and wrapping Django (`get_asgi_application()`) plus FastMCP's app in one Starlette router. The server extra of `fastmcp-slim` adds roughly a dozen packages not in the lock (authlib, joserfc, cyclopts, griffelib, jsonref, jsonschema-path, openapi-pydantic, py-key-value-aio, pyperclip, pyyaml, watchfiles, websockets ...; counted from `requires_dist`, not resolved).

### 3.3 Strands Agents (AWS)

**Not an MCP server framework.** It is an agent framework: its MCP support is a client (`MCPClient`) that loads a server's tools into a Strands agent ([Use MCP tools](https://strandsagents.com/docs/user-guide/sdk/tools/mcp-tools/), read 2026-10-18). Its "Implementing an MCP Server" section on that page is a four-line example with the SDK's own `FastMCP` (`from mcp.server import FastMCP`, the v1 API that no longer imports in `mcp` 2.x) and then points to the MCP docs. What it does serve is **A2A** (agent-to-agent protocol; "Serve agents over A2A", [llms.txt](https://strandsagents.com/llms.txt)), a different protocol, and its Shell product ships an MCP server for its own sandbox ([llms.txt](https://strandsagents.com/llms.txt)), not a framework for ours.
Version note: `strands-agents` 1.61.1 requires `mcp<2.2,>=1.23`, while Pipecat needs `mcp>=2.1.1`; only 2.1.x satisfies both, so adding it to the core's environment would downgrade `mcp` from 2.3.0 (inferred from `requires_dist`; whether Strands works on `mcp` 2.x: not checked).
Good for: building an agent **inside** Voice that consumes MCP tools (for example an assistant in the Portal that operates Voice through our own tool server). That is not in `PRODUCT.md` and not needed for exposing tools.

### 3.4 Django-specific libraries

| Library | Last release | What it wraps | Auth | Works with this repo's lock? |
|---|---|---|---|---|
| **django-stateless-mcp** (Ben Atkinson, MIT) | 0.1.11, 2026-08-31 (12 releases since 2026-07-29) | The SDK's `MCPServer`; `mcp_view(server)` is an ordinary Django view; `mcp.py` autodiscovery like `admin.py` | `token_verifier=` (SDK protocol), `required_scopes`, `user_resolver` sets `request.user`; bearer 401/403; view is CSRF-exempt by design | **Seen: yes** (below) |
| django-mcp-server (gts360 / omarbenhamid, MIT) | 0.5.7, 2025-10-10 | Old FastMCP from `mcp` 1.x; DRF views to tools | DRF authentication classes (`DJANGO_MCP_AUTHENTICATION_CLASSES`); OAuth via django-oauth-toolkit (+ DCR add-on) | **Seen: no.** `from mcp.server import FastMCP` raises `ImportError` on `mcp` 2.3.0 |
| django-mcp (kitespark, MIT) | 0.3.1, 2025-05-30 (0.3.2a1 2025-06-30) | `mcp` 1.x, needs an ASGI mount (`mount_mcp_server`) | none documented | No: `requires_dist` pins `mcp[cli]~=1.9.2` |
| mcp-django (joshuadavidthomas) | 0.14.0, 2026-07-23 | Depends on `fastmcp>=3.4.4`; its PyPI summary says it is an MCP server for Django integration with LLM assistants (a developer tool, not a way to expose an app's own tools; inferred from the summary) | n/a | not checked |
| bolt-mcp | 0.2.3, 2026-08-23 | django-bolt (a different Django-like stack) | n/a | No: needs django-bolt |
| djangorestframework-mcp-server | 0.52.1, 2026-10-16 | DRF plus `djangorestframework-services` | DRF | Not relevant: the Portal has no DRF |

Sources: PyPI JSON for each, [django-stateless-mcp README and docs](https://django-stateless-mcp.readthedocs.io/en/stable/), [django-mcp-server README](https://raw.githubusercontent.com/gts360/django-mcp-server/main/README.md), [django-mcp README](https://raw.githubusercontent.com/kitespark/django-mcp/main/README.md), read 2026-10-18. Commit counts, open issues and bus factor: **not checked** (the GitHub API is closed to this session). An aggregator said django-mcp-server had "no commits in roughly two months" ([SourcePulse](https://www.sourcepulse.org/projects/21887642)); PyPI shows nothing since 2025-10-10.

**What I ran** (scratchpad virtualenv, Python 3.13.16, `django==6.1.2`, `mcp==2.3.0`, `django-stateless-mcp==0.1.11`, as in the lock):
- Under real **gunicorn on WSGI with the Portal's flags** (`--workers 1 --threads 4 --no-control-socket`): a modern `tools/list`; a legacy `initialize` (`MCP-Protocol-Version: 2025-11-25`) answered 200 with no session id; a legacy `tools/call` with no session worked; `GET` answered 405; a bearer verifier gave 401 for no or bad token and 200 for a good one; `ToolAnnotations(destructive_hint=True)` came through in `tools/list`.
- The 401 body is `WWW-Authenticate: Bearer error="invalid_token", ...` **without** `resource_metadata` when only `token_verifier` is given (no `AuthSettings`). That is fine for a static header; OAuth discovery would need the well-known views written by hand.
- `from mcp.server import FastMCP` with `mcp` 2.3.0: `ImportError`, which is why django-mcp-server 0.5.7 does not load.
- Caveats: one process, one request at a time, no load; the library's README tests Django 5.2 and 6.0 and `mcp` 2.0.x, so Django 6.1 and `mcp` 2.3 are what I saw working, not what it promises. The view builds a session manager and an event loop per request under WSGI (library source and docs), which costs latency but needs no ASGI. Its `subscriptions/listen` stream answers 501 under WSGI (docs); no tool here needs it.
- Source size: `views.py` is about 400 lines (read); a hand-written equivalent over `streamable_http_app()` plus an ASGI move is the fallback if the package is abandoned (inferred).

### 3.5 Others, one line each

- **fastapi-mcp** 0.4.0 (2025-07-28): FastAPI endpoints to tools; the Portal is not FastAPI; `mcp>=1.12`. Skip.
- **mcp-use** 1.7.1 (2026-09-10): agent, client and server toolkit; requires `mcp<2.0.0` and langchain. Skip.
- **Hand-rolled on the SDK** is what sections 3.1 and 3.4 describe; the SDK's lowest level is `mcp.server.Server` with `on_list_tools`/`on_call_tool` handlers ([Low-level Server](https://py.sdk.modelcontextprotocol.io/advanced/low-level-server/)).

## 4. One server, tool list depends on the token

Wanted: Business tokens (read-only or full) and an operator token that additionally sees operator tools (invite, totals), on **one** endpoint; a hidden tool must also be refused when called anyway.

Spec: the tool set "MUST NOT vary per-connection or as a side effect of other requests on the connection. The set MAY vary by the authorization presented on the request — for example, returning only the tools the caller's granted scopes permit" ([Tools](https://modelcontextprotocol.io/specification/2026-07-28/server/tools), read 2026-10-18). So per-token lists are allowed. Servers MUST "implement proper access controls" and rate limit.

| | Hide from `tools/list` | Refuse a hidden tool when called | How |
|---|---|---|---|
| **Official SDK** | Yes, by middleware | Yes, by the same middleware | No per-tool `auth=` parameter in the docs I read. A middleware `(ctx, call_next)` reads `get_access_token()`, filters the `tools/list` result and raises `MCPError` on `tools/call`. The middleware API is "provisional" ([Middleware](https://py.sdk.modelcontextprotocol.io/advanced/middleware/)). **Seen** (below) |
| **FastMCP** (3.0.0 and later) | Yes: `@mcp.tool(auth=require_scopes("write"))`, or any callable on `AccessToken` scopes and claims | Yes: "the component is hidden from list responses and direct access returns not-found"; `AuthMiddleware` adds explicit `AuthorizationError` (and `insufficient_scope` challenges) on execution; checks combine with AND ([Authorization](https://gofastmcp.com/servers/authorization.md)) | Documented and built in; **not run** by me. Needs an `AuthProvider`, so a custom `TokenVerifier` for our tokens |
| **django-stateless-mcp** | Yes, `PermittedToolsFilter(is_visible)` | **No.** Its docs: "Hiding is not gating ... Nothing stops a client calling a hidden tool by name, so the tool must still gate its own execution" ([recipe](https://django-stateless-mcp.readthedocs.io/en/stable/recipes/oauth-and-permissions/)) | Keys on a Django **user** (`user.has_perm`); our callers are tokens with scopes, so a token-to-user mapping is extra work |
| django-mcp-server | Not found in its README | DRF permission classes guard the whole endpoint | not checked beyond the README |

**Seen** (same scratchpad setup, Django test client with real `django_stateless_mcp.mcp_view`, SDK middleware of about 20 lines, token verifier mapping three tokens to scopes `read`, `read write`, `read write operator`):
- `tools/list`: read token saw `list_calls`; write token `list_calls, remove_module`; operator token all four including `invite_business` and `totals`.
- `tools/call` of a hidden tool (`remove_module` with the read token, `invite_business` with the write token) answered `-32602 Unknown tool`, the same text as a tool that does not exist (`nonexistent`), so the refusal does not confirm the tool exists. The allowed calls returned results.
- A legacy-era request (`2025-11-25`) with the read token got the same filtered list and the same refusal.
- The permission table in the test was a closed set; a tool name missing from it was refused (fail closed, hard rules 3 and 4).

**One endpoint versus two.**

| | One endpoint, filter by token | Separate endpoints (Business `/mcp`, operator `/mcp/operator`) |
|---|---|---|
| Operator tools reachable from a Business token | Only if the filter is wrong; one function to test with a table of tools times token kinds | Not registered on the Business server at all: no code path |
| Read-only versus full | Same filter | Still needs a token-level split, or a third endpoint |
| What the operator configures in a client | One connector, one URL | Two connectors if they want both sets |
| Dependency on a provisional API | Yes (SDK middleware) unless FastMCP's `auth=` is used | No |
| Hard rule 2 (one way in per dangerous action) | Each tool also checks its own scope, so a filter bug is not the only gate | The tool function can still check; same cost |

My reading: one endpoint is workable and matches the request; keep the filter in one function, also check the scope inside each tool, and have a test that enumerates every tool against every token kind (hard rule 4). The operator split is the one place where a second server is cheap insurance.

## 5. Deployment shape

| Shape | What it takes | For | Against |
|---|---|---|---|
| **A. Django view in the Portal, as now (WSGI)** | `django-stateless-mcp` (or similar), one URL, one verifier. **Seen** to work under the exact gunicorn flags | No new app, host or image; same database and the same functions the views call (hard rule 2: one way in); Django `ALLOWED_HOSTS` is the host check | Young single-maintainer package; MCP calls share the Portal's 4 threads (Claude allows a tool call 240 s; [Build an MCP server for Claude](https://claude.com/docs/connectors/building/index.md)); one event loop per request |
| **B. Portal moves to ASGI, SDK app mounted** | `portal/asgi.py`, `uvicorn-worker` under gunicorn ([Django uvicorn](https://docs.djangoproject.com/en/6.1/howto/deployment/asgi/uvicorn/)), wrap Django and the SDK/FastMCP app in one Starlette router, host lifespan enters `session_manager.run()` | The documented SDK and FastMCP path; native async | Changes how the Portal runs (the login limiter assumes one worker); sync ORM from async tools needs `sync_to_async` (Django: "Do not call blocking synchronous functions ... in any async code") |
| **C. Second Dokploy app from `Dockerfile.portal`** with an MCP-only URL conf | New app, host, deploy setting | MCP load and a stuck tool cannot starve the Portal's pages | A new app or host is a "Stop and ask" item (`CLAUDE.md`); two places that load the Django app |
| **D. Inside the core** | MCP routes in `voice/serve.py` | n/a | The core has no database and no Businesses' tokens; it would need the Portal for every check, coupling the call path to the Portal and putting tool traffic on the call process's loop (ADR 0002: "a Portal restart or a heavy page never cuts a live call") |

**Which service hosts what.** The Portal owns Businesses, settings, Modules, call records, the test-call ticket and the operator pages, so Portal tools live in the Portal. The core "takes no actions" (ADR 0001) and keeps nothing a Business edits: today a Business can only start a call (a browser with a microphone through a Portal ticket) and the core hangs it up at 10 minutes. I found no core action a Business can take that an agent would need as a tool (inferred from `ARCHITECTURE.md`; **Petter should confirm**). So the first version has **no MCP in the core**. A test call is also not a good tool: it needs a person's microphone and spends Gemini credit (`CLAUDE.md`, Stop and ask: spend). If a live-call control is ever wanted, expose it from the Portal, or add it as a separate small surface in the core behind the call ticket; neither is designed here.

## 6. Tool annotations and dangerous actions

- Fields: `title`, `readOnlyHint` (default false), `destructiveHint` (default **true**, meaningful only when not read-only), `idempotentHint`, `openWorldHint` ([schema](https://modelcontextprotocol.io/specification/2026-07-28/schema), read 2026-10-18). So an unannotated tool counts as a destructive write. The spec: "clients **MUST** consider tool annotations to be untrusted unless they come from trusted servers"; "Clients should never make tool use decisions based on ToolAnnotations received from untrusted servers"; and there SHOULD be a human in the loop with the ability to deny invocations ([Tools](https://modelcontextprotocol.io/specification/2026-07-28/server/tools)). The SDK: "They are hints, not security. Never rely on a client honouring them" ([Tools](https://py.sdk.modelcontextprotocol.io/servers/tools/)).
- Claude: its directory review criteria require `title` plus `readOnlyHint: true` or `destructiveHint: true` on every tool, "These determine auto-permissions in Claude. Read-only tools can run without per-call confirmation, and destructive tools always prompt" ([Review criteria](https://claude.com/docs/connectors/building/review-criteria.md), read 2026-10-18). Users can also set a tool to Blocked per connector ([Add a connector](https://claude.com/docs/connectors/custom/add-unlisted)). Whether a custom (non-directory) connector gets the same auto-permissions, and what Claude Code does with the hints: not checked.
- ChatGPT: "ChatGPT currently requires manual confirmation in any conversation before write actions can be taken", write actions "can still occur even if a tool is tagged as read-only" ([MCP docs](https://developers.openai.com/api/docs/mcp), read 2026-10-18); annotations "help ChatGPT and Codex choose appropriate confirmation and safety behavior. They do not replace authorization, validation, or confirmation in your server" ([Build an MCP server](https://developers.openai.com/plugins/build/mcp-server.md), read 2026-10-18). Its guidance: `destructiveHint: true` for "irreversible or difficult to reverse outcomes".
- Consequence for hard rules 1 to 3: annotations are UX only. The refusal of a write by a read-only token, of a Business A token on Business B's data, and of an operator tool by a Business token has to sit in the server (token scope, then the same Portal function and database constraint the web page goes through). Mapping for the first tools (suggestion): list and read tools `readOnlyHint`; `remove_module` `destructiveHint`; settings update overwrites the Business's facts, which the schema's wording ("only additive updates" for `destructiveHint: false`) counts as destructive (inferred).

## 7. "Accounted"

**Identified with reasonable confidence, not certainty: [accounted.se](https://www.accounted.se/)**, a Swedish open-source (AGPL-3.0) double-entry ledger by Arcim Technology AB with a REST API and an MCP server, hosted at app.accounted.se, code at `erp-mafia/accounted` ([MCP server card](https://www.accounted.se/.well-known/mcp-server-card), [llms.txt](https://www.accounted.se/llms.txt), read 2026-10-18). Why I think it is the one: Voice targets small Swedish businesses, `PRODUCT.md` names only "Accounted", and this product is built around exposing every action to agents. Other products found while searching, not matching the name: Accountable (accountable.im), DualEntry, Layer, AgenticBooks. Its earlier name is "gnubok" (the key prefix `gnubok_sk_` and some tool names still say so). **Petter to confirm it is this one.**

How it exposes its actions ([Connect with Claude](https://www.accounted.se/docs/api/connect-claude), [blog on its MCP server](https://www.accounted.se/blogg/mcp-server-bokforing), [README](https://raw.githubusercontent.com/erp-mafia/accounted/main/README.md), read 2026-10-18):
- **One endpoint**, `https://app.accounted.se/api/extensions/ext/mcp-server/mcp?tool_namespace=accounted`; `tool_namespace` selects tool names (`accounted_*`).
- **Granularity**: fine-grained verbs, 150+ tools (docs) of which about 130 are in the default `tools/list` and the rest are found with a search tool; names such as `categorize_transaction`, `get_ar_ledger`, `close_period`; plus about ten `accounted://` resources and workflow "skills" the agent loads on demand. The REST API has 280+ endpoints, so the tool set is smaller than a one-to-one mirror (the blog says tools are "grouped by domain").
- **Writes never commit**: every write tool returns a `pending_operation` with `risk_level` (low, medium, high); a human approves in chat or on a `/pending` page; high risk cannot be approved in bulk and needs a typed confirmation; there is no auto-commit setting ("removed in May 2026"); a key that can both stage and approve is refused at creation unless the user confirms; `dry_run` and `idempotency_key` arguments on write tools. Every write is audit-logged with the proposing agent session and the approving person.
- **Auth, three paths**: (A) claude.ai or Claude Desktop custom connector over OAuth 2.1 with PKCE and DCR (consent page with all scopes pre-selected, "Endast läs" for read-only; sign in with BankID or e-mail plus 2FA); (B) Claude Code plugin (`/plugin marketplace add erp-mafia/accounted`) with eight workflow commands, then `/mcp` sign-in; (C) API key through an `npx accounted-mcp` stdio bridge, because a key cannot be typed into claude.ai. Keys are scoped (`transactions:read`, `invoices:write`, ...); a `..._test_` key reads real data but forces every write into dry-run. **Without read scopes the write tools do not appear in the tool list.**
- **Setup flow for the user's agent**: a link that opens claude.ai's "Add custom connector" with name and URL pre-filled (it "grants nothing on its own"). One gotcha they document: the URL needs `auth=required`, or Claude's dialog suggests "No sign-in" and never opens the login. Several companies per sign-in; `?company=<id>` on the URL locks a connection to one company.
- Stack (README): Next.js 16, TypeScript, Supabase/Postgres with row-level security. So the code is not reusable for a Django Portal; the shape is.

What Voice can take from it (suggestions, not decisions): per-token scope that hides write tools; a read-only first connection; one pre-filled "connect" link on the Portal; a second path for API-key users because claude.ai cannot send a header yet; a human-approval stage for the riskiest actions (that would be a product decision).

## Recommendation

**Framework: the official MCP Python SDK (`mcp` 2.x, `MCPServer`), with `django-stateless-mcp` as the Django glue.** It is already a dependency, MIT, the same decorators and the same `TokenVerifier`, and the glue served both protocol eras and bearer checks under the Portal's exact gunicorn command. Tools are plain functions that call the same Portal functions the views call (hard rule 2).

**Deployment: a Django view in the existing Portal** (shape A), no core MCP, no new Dokploy app. Pin `django-stateless-mcp` exactly, put one test per tool and token kind beside the Portal tests (`tests/portal/`), and keep the tool functions in one module so shape B or C is a move, not a rewrite.

**Auth for the first version: a per-Business bearer token minted in the Portal**, stored hashed with a database constraint, shown once, revocable, with scope `read` or `write`; a separate issuance path for the operator token. It reaches Claude Code (`--header`), scripts and API agents, and self-hosters. It does **not** reach ChatGPT at all, and reaches claude.ai only through the beta Request headers field (limited organizations). Owners on claude.ai (the primary users in `PRODUCT.md`) need OAuth to connect with a click.

**Runner-up and the trade-off.**
- Framework: **FastMCP 4** has the better built-in pieces for this exact job (per-tool `auth=` that hides and refuses, `AuthMiddleware`, token verifiers, providers, in-memory test client). Against it: a second dependency tree that moves quickly (21 releases of the 4.x line since 2026-07-21), no Django integration, so the Portal would have to move to ASGI (shape B); and it still does not provide the authorization server that full OAuth needs. Pick it if the per-token filtering middleware (provisional in the SDK) turns out to break in a 2.x minor release.
- Auth: **OAuth through the Portal as authorization server** (django-oauth-toolkit plus DCR or CIMD, well-known views, consent page) would let a claude.ai owner connect with one click, and ChatGPT work. It is a larger security-sensitive piece of work (my estimate, not measured), and an external identity provider would be a new vendor, which `CLAUDE.md` makes Petter's call. The verifier is the seam, so the tools do not change when it arrives.
- Per-token visibility: one endpoint with one filtering function and a tools-by-tokens test, or two endpoints; the operator split is the case for a second server.

## Not checked

- GitHub activity (commits, open issues, maintainers) of every library: the GitHub API is not open to this session. Maintenance claims rest on PyPI release dates and an aggregator page.
- django-stateless-mcp under Django 6.1 and `mcp` 2.3 beyond the single-process runs above; under load; with an OAuth `AuthSettings`; whether it keeps working across `mcp` 2.x minors (its README states 2.0.x).
- Whether claude.ai, Claude Code v1 or v2 runtime, and ChatGPT actually connect to a server built this way. The legacy and modern JSON-RPC exchanges were driven with curl and the Django test client, not with a real client. This is the "seen to hold" step (hard rule 7).
- FastMCP 4 itself: nothing from it was installed or run; its per-component `auth=` and `AuthMiddleware` behaviour is from its docs.
- Whether Claude's request-headers field is available to a given organization or plan; how claude.ai caches `tools/list` after a token's scope changes; whether claude.ai uses the 2026-07-28 transport today; how Claude Code uses `readOnlyHint` and `destructiveHint`; whether custom connectors get the directory's auto-permission rule.
- The Anthropic API's own MCP connector (token passing) and Cursor; OAuth libraries for Django (django-oauth-toolkit and its DCR add-on) beyond the README line that names them.
- Whether the SDK's `mcp.server` has a built-in per-tool auth parameter in a release newer than the docs I read.
- Strands on `mcp` 2.x.
- Whether any action exists in the core that a Business's agent should control (inferred none).
- That the product is accounted.se (identified from the name, language and fit; not confirmed by Petter).
