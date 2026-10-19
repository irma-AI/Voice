"""The settings port: where the core learns which Business a call is for, and what it may say.

One interface, `load_settings()`, and two adapters chosen by the environment: the Portal's settings
address, or a file in the same shape (contract/business-settings.schema.json) for evals.
Anything else (nothing set, both set, the Portal down, a reply that breaks the shape) raises
`SettingsRefused`, and the caller refuses the call: a fallback could serve another Business's instructions, or
one that was switched off (ADR 0002). The Portal never imports this, and this never imports the Portal.
"""

import json
import os
import re
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
INSTRUCTIONS_MAX = 5000
MODULES_MAX = 10
MODULE_NAME_MAX = 100
MODULE_URL_MAX = 2000
MODULE_COMMAND_MAX = 500
MODULE_ARGS_MAX = 20
MODULE_ARG_MAX = 500
COLOUR_PATTERN = (
    r"#[0-9a-f]{6}"  # the schema's theme accent and accent_text, anchored there
)
LOGO_URL_MAX = 2000
PRIVACY_URL_MAX = 2000
PRIVACY_URL_PATTERN = r"https://\S+"  # the schema's privacy_url, anchored there
# ponytail: a call waits this long in silence for the Portal before it is refused; make it a setting if the Portal is slow in practice.
PORTAL_TIMEOUT_S = 5
MAX_REPLY_BYTES = (
    64_000  # a reply longer than the schema allows is cut and then fails to parse
)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect would carry the secret to wherever it points; a moved Portal is a refused call."""

    def redirect_request(self, *_: Any, **__: Any) -> None:
        return None


class SettingsRefused(Exception):
    """No safe settings for this call. The message goes in the log, so it holds no instructions and no secret."""


@dataclass(frozen=True)
class Module:
    """One MCP server the Business's agent may use: a remote one by `url`, a local one by `command`."""

    name: str
    url: str | None = None
    command: str | None = None
    args: tuple[str, ...] = ()


@dataclass(frozen=True)
class Theme:
    """The Business's look for its Callers: an accent (already made readable under `accent_text` by the Portal) and a logo address, each optional."""

    accent: str | None = None
    accent_text: str | None = None
    logo_url: str | None = None


@dataclass(frozen=True)
class Settings:
    name: str
    instructions: str
    languages: tuple[str, ...]
    modules: tuple[Module, ...] = ()
    theme: Theme = Theme()
    # The Business's own privacy notice, linked on the call page; None for no link.
    privacy_url: str | None = None


def _theme(data: object) -> Theme:
    if not isinstance(data, dict):
        raise SettingsRefused("the theme is not a JSON object")
    d: dict[str, Any] = data  # pyright: ignore[reportUnknownVariableType]
    if set(d) - {"accent", "accent_text", "logo_url"} or (
        ("accent" in d) != ("accent_text" in d)
    ):
        raise SettingsRefused(
            "the theme has an accent with its text colour, a logo_url, or both"
        )
    for key in {"accent", "accent_text"} & set(d):
        if not (isinstance(d[key], str) and re.fullmatch(COLOUR_PATTERN, d[key])):
            raise SettingsRefused("a theme colour is not # and six hex digits")
    if "logo_url" in d and not (
        isinstance(d["logo_url"], str)
        and len(d["logo_url"]) <= LOGO_URL_MAX
        and d["logo_url"].startswith(("http://", "https://"))
    ):
        raise SettingsRefused("the theme's logo_url is not a short http address")
    return Theme(d.get("accent"), d.get("accent_text"), d.get("logo_url"))


def _privacy_url(value: object) -> str:
    if not (
        isinstance(value, str)
        and len(value) <= PRIVACY_URL_MAX
        and re.fullmatch(PRIVACY_URL_PATTERN, value)
    ):
        raise SettingsRefused("the privacy_url is not a short https address")
    return value


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
        not {"name", "instructions", "languages"}
        <= set(d)
        <= {"name", "instructions", "languages", "modules", "theme", "privacy_url"}
    ):
        raise SettingsRefused(
            "settings do not have name, instructions and languages, and at most modules, a theme and a privacy_url besides"
        )
    name, instructions, languages = d["name"], d["instructions"], d["languages"]
    raw_modules = d.get("modules", [])
    if not (isinstance(raw_modules, list) and len(raw_modules) <= MODULES_MAX):  # pyright: ignore[reportUnknownArgumentType]
        raise SettingsRefused("settings modules are not a short list")
    modules = cast("list[object]", raw_modules)
    if not (isinstance(name, str) and 1 <= len(name) <= NAME_MAX):
        raise SettingsRefused("settings name is missing or too long")
    if not (isinstance(instructions, str) and len(instructions) <= INSTRUCTIONS_MAX):
        raise SettingsRefused("settings instructions are not text or too long")
    if not (
        isinstance(languages, list)
        and languages
        and all(isinstance(lang, str) and lang in LANGUAGES for lang in languages)  # pyright: ignore[reportUnknownVariableType]
    ):
        raise SettingsRefused("settings languages are empty or not known")
    return Settings(
        name,
        instructions,
        tuple(languages),  # pyright: ignore[reportUnknownArgumentType]
        tuple(_module(m) for m in modules),
        _theme(d["theme"]) if "theme" in d else Theme(),
        _privacy_url(d["privacy_url"]) if "privacy_url" in d else None,
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
        raise SettingsRefused("the Business's number is not a number")
    address = f"{url.rstrip('/')}/api/settings/{business_id}/"
    try:
        request = urllib.request.Request(
            address, headers={"Authorization": f"Bearer {secret}"}
        )
        with urllib.request.build_opener(NoRedirect).open(
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

    `business_id` names the Business a ticket was signed for (voice/ticket.py). The Portal serves only a named
    Business, and a file only the eval Channel, which names none: a file holds one Business's settings, which
    would be another's for a named one.
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
        if business_id is None:
            raise SettingsRefused("the call names no Business")
        secret = env.get("CORE_SECRET", "")
        if not secret:
            raise SettingsRefused("SETTINGS_URL is set but CORE_SECRET is missing")
        return _from_portal(portal, secret, business_id.strip())
    raise SettingsRefused(
        "no settings source: set SETTINGS_URL (with CORE_SECRET), or SETTINGS_FILE for evals"
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
