"""The settings port: where the core learns which Business a call is for, and what it may say.

One interface, `load_settings()`, and two adapters chosen by the environment: the Portal's settings
address, or a file in the same shape (contract/business-settings.schema.json) for evals and local runs.
Anything else (nothing set, both set, the Portal down, a reply that breaks the shape) raises
`SettingsRefused`, and the caller refuses the call: a fallback could serve another Business's facts, or
one that was switched off (ADR 0002). The Portal never imports this, and this never imports the Portal.
"""

import http.client
import json
import os
import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit

# Edit with contract/business-settings.schema.json: tests/test_settings_port.py reads both and fails on drift.
LANGUAGES = {"sv": "Swedish", "en": "English"}
NAME_MAX = 200
FACTS_MAX = 5000
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
class Settings:
    name: str
    facts: str
    languages: tuple[str, ...]


def parse(data: object) -> Settings:
    """Checks one settings reply against the shape in contract/business-settings.schema.json."""
    if not isinstance(data, dict):
        raise SettingsRefused("settings are not a JSON object")
    d: dict[str, Any] = data  # pyright: ignore[reportUnknownVariableType]
    if set(d) != {"name", "facts", "languages"}:
        raise SettingsRefused("settings do not have exactly name, facts and languages")
    name, facts, languages = d["name"], d["facts"], d["languages"]
    if not (isinstance(name, str) and 1 <= len(name) <= NAME_MAX):
        raise SettingsRefused("settings name is missing or too long")
    if not (isinstance(facts, str) and len(facts) <= FACTS_MAX):
        raise SettingsRefused("settings facts are not text or too long")
    if not (
        isinstance(languages, list)
        and languages
        and all(lang in LANGUAGES for lang in languages)  # pyright: ignore[reportUnknownVariableType]
    ):
        raise SettingsRefused("settings languages are empty or not known")
    return Settings(name, facts, tuple(languages))  # pyright: ignore[reportUnknownArgumentType]


def _from_file(path: str) -> Settings:
    try:
        return parse(json.loads(Path(path).read_text("utf-8")))
    except (OSError, ValueError) as e:
        raise SettingsRefused(f"settings file {path} cannot be read: {e}") from None


def _from_portal(url: str, secret: str, business_id: str) -> Settings:
    # The id is the Portal's database id until VOI-29 adds the public call link.
    address = f"{url.rstrip('/')}/api/settings/{quote(business_id, safe='')}/"
    request = urllib.request.Request(
        address, headers={"Authorization": f"Bearer {secret}"}
    )
    try:
        with urllib.request.build_opener(_NoRedirect).open(
            request, timeout=PORTAL_TIMEOUT_S
        ) as reply:
            return parse(json.loads(reply.read(MAX_REPLY_BYTES)))
    except urllib.error.HTTPError as e:
        raise SettingsRefused(f"the Portal answered {e.code} for {address}") from None
    except (
        OSError,
        ValueError,
        http.client.HTTPException,
    ) as e:  # unreachable, timed out, cut short, or not JSON
        raise SettingsRefused(
            f"the Portal at {address} gave no settings: {e}"
        ) from None


def load_settings(env: Mapping[str, str] = os.environ) -> Settings:
    """The settings for the next call, read fresh each time so a Portal change shows up in it."""
    portal = env.get("PORTAL_URL", "").strip()
    file = env.get("SETTINGS_FILE", "").strip()
    if portal and file:
        raise SettingsRefused(
            "both PORTAL_URL and SETTINGS_FILE are set: set only one settings source"
        )
    if file:
        return _from_file(file)
    if portal:
        secret, business = (
            env.get("CORE_SECRET", ""),
            env.get("BUSINESS_ID", "").strip(),
        )
        if not secret or not business:
            raise SettingsRefused(
                "PORTAL_URL is set but CORE_SECRET or BUSINESS_ID is missing"
            )
        return _from_portal(portal, secret, business)
    raise SettingsRefused(
        "no settings source: set PORTAL_URL (with CORE_SECRET and BUSINESS_ID), or SETTINGS_FILE for evals and local runs"
    )


def describe_source(env: Mapping[str, str] = os.environ) -> str:
    """One line for the start-up log: which source calls will use, or that they will be refused."""
    portal = env.get("PORTAL_URL", "").strip()
    file = env.get("SETTINGS_FILE", "").strip()
    if portal and file:
        return "settings: both PORTAL_URL and SETTINGS_FILE are set, so every call will be refused"
    if file:
        return f"settings: file {file}"
    if portal:
        return f"settings: the Portal at {urlsplit(portal).hostname}"  # never the whole address: it could hold a password
    return "settings: no source set (PORTAL_URL or SETTINGS_FILE), so every call will be refused"
