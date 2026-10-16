"""The settings port: where the core learns which Business a call is for, and what it may say.

One interface, `load_settings()`, and two adapters chosen by the environment: the Portal's settings
address, or a file in the same shape (contract/business-settings.schema.json) for evals and local runs.
Anything else (nothing set, both set, the Portal down, a reply that breaks the shape) raises
`SettingsRefused`, and the caller refuses the call: a fallback could serve another Business's facts, or
one that was switched off (ADR 0002). The Portal never imports this, and this never imports the Portal.
"""

import json
import os
import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit

# Edit with contract/business-settings.schema.json: tests/test_settings_port.py reads both and fails on drift.
LANGUAGES = {"sv": "Swedish", "en": "English"}
NAME_MAX = 200
FACTS_MAX = 5000
MODULES_MAX = 10
MODULE_NAME_MAX = 100
MODULE_URL_MAX = 2000
MODULE_COMMAND_MAX = 500
MODULE_ARGS_MAX = 20
MODULE_ARG_MAX = 500
# ponytail: a call waits this long in silence for the Portal before it is refused; make it a setting if the Portal is slow in practice.
PORTAL_TIMEOUT_S = 5
MAX_REPLY_BYTES = (
    64_000  # a reply longer than the schema allows is cut and then fails to parse
)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect would carry the secret to wherever it points; a moved Portal is a refused call."""

    def redirect_request(self, *_: Any, **__: Any) -> None:
        return None


class SettingsRefused(Exception):
    """No safe settings for this call. The message goes in the log, so it holds no facts and no secret."""


@dataclass(frozen=True)
class Module:
    """One MCP server the Business's agent may use: a remote one by `url`, a local one by `command`."""

    name: str
    url: str | None = None
    command: str | None = None
    args: tuple[str, ...] = ()


@dataclass(frozen=True)
class Settings:
    name: str
    facts: str
    languages: tuple[str, ...]
    modules: tuple[Module, ...] = ()


def _text(value: object, longest: int) -> str:
    if not (isinstance(value, str) and 1 <= len(value) <= longest):
        raise SettingsRefused(
            "a Module's name, address or command is missing or too long"
        )
    return value


def _module(data: object) -> Module:
    if not isinstance(data, dict):
        raise SettingsRefused("a Module is not a JSON object")
    d: dict[str, Any] = data  # pyright: ignore[reportUnknownVariableType]
    name = _text(d.get("name"), MODULE_NAME_MAX)
    if set(d) == {"name", "url"}:
        url = _text(d["url"], MODULE_URL_MAX)
        if not url.startswith(("http://", "https://")):
            raise SettingsRefused("a Module's address must be an http or https address")
        return Module(name, url=url)
    if set(d) - {"name", "command", "args"} or "command" not in d:
        raise SettingsRefused("a Module has a url, or a command with optional args")
    raw = d.get("args", [])
    args = cast("list[Any]", raw) if isinstance(raw, list) else None
    if (
        args is None
        or len(args) > MODULE_ARGS_MAX
        or not all(isinstance(a, str) and len(a) <= MODULE_ARG_MAX for a in args)
    ):
        raise SettingsRefused("a Module's args are not a short list of text")
    command = _text(d["command"], MODULE_COMMAND_MAX)
    return Module(name, command=command, args=tuple(cast("list[str]", args)))


def parse(data: object) -> Settings:
    """Checks one settings reply against the shape in contract/business-settings.schema.json."""
    if not isinstance(data, dict):
        raise SettingsRefused("settings are not a JSON object")
    d: dict[str, Any] = data  # pyright: ignore[reportUnknownVariableType]
    if (
        not {"name", "facts", "languages"}
        <= set(d)
        <= {"name", "facts", "languages", "modules"}
    ):
        raise SettingsRefused(
            "settings do not have name, facts and languages, and at most modules besides"
        )
    name, facts, languages = d["name"], d["facts"], d["languages"]
    raw_modules = d.get("modules", [])
    if not (isinstance(raw_modules, list) and len(raw_modules) <= MODULES_MAX):  # pyright: ignore[reportUnknownArgumentType]
        raise SettingsRefused("settings modules are not a short list")
    modules = cast("list[object]", raw_modules)
    if not (isinstance(name, str) and 1 <= len(name) <= NAME_MAX):
        raise SettingsRefused("settings name is missing or too long")
    if not (isinstance(facts, str) and len(facts) <= FACTS_MAX):
        raise SettingsRefused("settings facts are not text or too long")
    if not (
        isinstance(languages, list)
        and languages
        and all(isinstance(lang, str) and lang in LANGUAGES for lang in languages)  # pyright: ignore[reportUnknownVariableType]
    ):
        raise SettingsRefused("settings languages are empty or not known")
    return Settings(
        name,
        facts,
        tuple(languages),  # pyright: ignore[reportUnknownArgumentType]
        tuple(_module(m) for m in modules),
    )


def _from_file(path: str) -> Settings:
    try:
        return parse(json.loads(Path(path).read_text("utf-8")))
    except SettingsRefused:
        raise
    except Exception as e:  # noqa: BLE001  fail closed: unreadable, not JSON, too deep: all refuse
        raise SettingsRefused(
            f"settings file {path} cannot be read ({type(e).__name__})"
        ) from None


def _from_portal(url: str, secret: str, business_id: str) -> Settings:
    parts = urlsplit(url)
    host = (
        parts.hostname
    )  # the log names the host only: the address could hold a password
    if parts.scheme not in ("http", "https") or not host:
        raise SettingsRefused("SETTINGS_URL must be an http or https address")
    # The id is the Portal's database id until VOI-29 adds the public call link.
    if not business_id.isascii() or not business_id.isdigit():
        raise SettingsRefused("BUSINESS_ID must be the Business's number in the Portal")
    address = f"{url.rstrip('/')}/api/settings/{business_id}/"
    try:
        request = urllib.request.Request(
            address, headers={"Authorization": f"Bearer {secret}"}
        )
        with urllib.request.build_opener(_NoRedirect).open(
            request, timeout=PORTAL_TIMEOUT_S
        ) as reply:
            return parse(json.loads(reply.read(MAX_REPLY_BYTES)))
    except SettingsRefused:
        raise
    except urllib.error.HTTPError as e:
        raise SettingsRefused(f"the Portal at {host} answered {e.code}") from None
    except Exception as e:  # noqa: BLE001  fail closed: unreachable, cut short, not JSON, too deep: all refuse, and only the kind is logged (a message could hold the secret)
        raise SettingsRefused(
            f"the Portal at {host} gave no settings ({type(e).__name__})"
        ) from None


def load_settings(
    env: Mapping[str, str] = os.environ, business_id: str | None = None
) -> Settings:
    """The settings for the next call, read fresh each time so a Portal change shows up in it.

    `business_id` names the Business a ticket was signed for (voice/ticket.py) and wins over BUSINESS_ID. Only the
    Portal can serve a named Business: a file holds one Business's settings, which would be another's here.
    """
    portal = env.get("SETTINGS_URL", "").strip()
    file = env.get("SETTINGS_FILE", "").strip()
    if portal and file:
        raise SettingsRefused(
            "both SETTINGS_URL and SETTINGS_FILE are set: set only one settings source"
        )
    if file:
        if business_id is not None:
            raise SettingsRefused(
                "a call for a named Business needs the Portal, but only SETTINGS_FILE is set"
            )
        return _from_file(file)
    if portal:
        secret, business = (
            env.get("CORE_SECRET", ""),
            (
                env.get("BUSINESS_ID", "") if business_id is None else business_id
            ).strip(),
        )
        if not secret or not business:
            raise SettingsRefused(
                "SETTINGS_URL is set but CORE_SECRET or BUSINESS_ID is missing"
            )
        return _from_portal(portal, secret, business)
    raise SettingsRefused(
        "no settings source: set SETTINGS_URL (with CORE_SECRET and BUSINESS_ID), or SETTINGS_FILE for evals and local runs"
    )


def describe_source(env: Mapping[str, str] = os.environ) -> str:
    """One line for the start-up log: which source calls will use, or that they will be refused."""
    portal = env.get("SETTINGS_URL", "").strip()
    file = env.get("SETTINGS_FILE", "").strip()
    if portal and file:
        return "settings: both SETTINGS_URL and SETTINGS_FILE are set, so every call will be refused"
    if file:
        return f"settings: file {file}"
    if portal:
        return f"settings: the Portal at {urlsplit(portal).hostname}"  # never the whole address: it could hold a password
    return "settings: no source set (SETTINGS_URL or SETTINGS_FILE), so every call will be refused"
