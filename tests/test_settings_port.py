"""Seam 2: the settings port, free. Parsing, choosing a source, refusing, and the prompt built from one Business.

The Portal adapter talks to a real HTTP server on localhost standing in for the Portal; nothing of ours is mocked.
"""

import json
from collections.abc import Generator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Thread
from typing import Any

import pytest
from dotenv import dotenv_values

from tests.evals.checks import BUSINESS_FILE, MODULE_BUSINESS_FILE
from tests.portal.contract import SCHEMA, schema_errors
from voice.agent import DISCLOSURE, REFUSAL, refusal_instruction, system_instruction
from voice.settings import (
    COLOUR_PATTERN,
    FACTS_MAX,
    LANGUAGES,
    LOGO_URL_MAX,
    MODULE_ARG_MAX,
    MODULE_ARGS_MAX,
    MODULE_COMMAND_MAX,
    MODULE_NAME_MAX,
    MODULE_URL_MAX,
    MODULES_MAX,
    NAME_MAX,
    PRIVACY_URL_MAX,
    PRIVACY_URL_PATTERN,
    Module,
    Settings,
    SettingsRefused,
    Theme,
    describe_source,
    load_settings,
    parse,
)

GOOD: dict[str, Any] = {
    "name": "Anna's Salon",
    "facts": "Öppet 8-17.",
    "languages": ["sv", "en"],
}


@contextmanager
def fake_portal(
    status: int = 200, body: object = GOOD, paths: list[str] | None = None
) -> Generator[str]:
    """A real server that answers like the Portal's settings address: Bearer `s3cret`, or 401."""
    seen: list[str] = [] if paths is None else paths  # the addresses asked for

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            seen.append(self.path)
            ok = self.headers.get("Authorization") == "Bearer s3cret"
            self.send_response(status if ok else 401)
            if status == 302:
                self.send_header("Location", "http://127.0.0.1:1/elsewhere")
            self.end_headers()
            self.wfile.write(json.dumps(body if ok else {"error": "no"}).encode())

        def log_message(self, format: str, *args: object) -> None:
            return None

    server = HTTPServer(("127.0.0.1", 0), Handler)
    Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()


REMOTE: dict[str, Any] = {"name": "booking", "url": "https://modules.example/mcp"}
LOCAL: dict[str, Any] = {"name": "hours", "command": "python", "args": ["-m", "x"]}


def portal_env(url: str) -> dict[str, str]:
    return {"SETTINGS_URL": url, "CORE_SECRET": "s3cret"}


# --- the shape: one definition in contract/, the core's copy of its limits must agree ---


def test_the_cores_limits_match_the_schema() -> None:
    props = SCHEMA["properties"]
    assert set(LANGUAGES) == set(props["languages"]["items"]["enum"]), (
        "edit LANGUAGES in voice/settings.py or the schema's language enum: they must list the same languages"
    )
    assert NAME_MAX == props["name"]["maxLength"], (
        "edit NAME_MAX or the schema's name maxLength"
    )
    assert FACTS_MAX == props["facts"]["maxLength"], (
        "edit FACTS_MAX or the schema's facts maxLength"
    )
    assert set(SCHEMA["required"]) == {"name", "facts", "languages"}
    modules = props["modules"]
    remote, local = modules["items"]["oneOf"]
    for core, schema, what in [
        (MODULES_MAX, modules["maxItems"], "modules maxItems"),
        (MODULE_NAME_MAX, remote["properties"]["name"]["maxLength"], "a Module's name"),
        (MODULE_URL_MAX, remote["properties"]["url"]["maxLength"], "a Module's url"),
        (MODULE_COMMAND_MAX, local["properties"]["command"]["maxLength"], "command"),
        (MODULE_ARGS_MAX, local["properties"]["args"]["maxItems"], "args maxItems"),
        (MODULE_ARG_MAX, local["properties"]["args"]["items"]["maxLength"], "an arg"),
    ]:
        assert core == schema, f"edit the core's limit or the schema's for {what}"
    theme = props["theme"]["properties"]
    assert (
        theme["accent"]["pattern"]
        == theme["accent_text"]["pattern"]
        == f"^{COLOUR_PATTERN}$"
    ), "edit COLOUR_PATTERN in voice/settings.py or the schema's theme colour patterns"
    assert LOGO_URL_MAX == theme["logo_url"]["maxLength"], (
        "edit LOGO_URL_MAX or the schema's logo_url maxLength"
    )
    assert props["privacy_url"]["pattern"] == f"^{PRIVACY_URL_PATTERN}$", (
        "edit PRIVACY_URL_PATTERN in voice/settings.py or the schema's privacy_url pattern"
    )
    assert PRIVACY_URL_MAX == props["privacy_url"]["maxLength"], (
        "edit PRIVACY_URL_MAX or the schema's privacy_url maxLength"
    )


THEME_CASES: list[Any] = [
    {},
    {"accent": "#1a2a44", "accent_text": "#ffffff"},
    {"logo_url": "https://portal.example/logo/abc/"},
    {
        "accent": "#1a2a44",
        "accent_text": "#ffffff",
        "logo_url": "http://localhost:8000/logo/abc/",
    },
    {"accent": "#1a2a44"},
    {"accent_text": "#ffffff"},
    {"accent": "#1A2A44", "accent_text": "#ffffff"},
    {"accent": "1a2a44", "accent_text": "#ffffff"},
    {"accent": "#1a2a4", "accent_text": "#ffffff"},
    {"accent": "red", "accent_text": "#ffffff"},
    {"accent": 5, "accent_text": "#ffffff"},
    {"logo_url": "javascript:alert(1)"},
    {"logo_url": "https://" + "x" * LOGO_URL_MAX},
    {"logo_url": None},
    {"logo": "https://x"},
    "not an object",
]


PRIVACY_URL_CASES: list[Any] = [
    "https://example.se/integritet",
    "https://example.se/privacy?lang=sv#callers",
    "https://" + "x" * (PRIVACY_URL_MAX - len("https://")),
    "https://" + "x" * (PRIVACY_URL_MAX - len("https://") + 1),
    "http://example.se/privacy",
    "https://example.se/privacy policy",
    "https://example.se/privacy\r\nSet-Cookie: x=1",
    "https://",
    "javascript:alert(1)",
    "",
    None,
    5,
]


MODULE_CASES: list[Any] = [
    [],
    [REMOTE],
    [LOCAL],
    [{"name": "m", "command": "x"}],
    [REMOTE] * MODULES_MAX,
    [REMOTE] * (MODULES_MAX + 1),
    "not a list",
    ["not an object"],
    [{"name": "m"}],
    [{"name": "", "url": "http://x"}],
    [{"name": "m" * (MODULE_NAME_MAX + 1), "url": "http://x"}],
    [{"name": "m", "url": "ftp://x"}],
    [{"name": "m", "url": "http://" + "x" * MODULE_URL_MAX}],
    [{"name": "m", "url": "http://x", "command": "x"}],
    [{"name": "m", "url": "http://x", "args": []}],
    [{"name": "m", "command": ""}],
    [{"name": "m", "command": "x" * (MODULE_COMMAND_MAX + 1)}],
    [{"name": "m", "command": "x", "args": [1]}],
    [{"name": "m", "command": "x", "args": ["a"] * MODULE_ARGS_MAX}],
    [{"name": "m", "command": "x", "args": ["a"] * (MODULE_ARGS_MAX + 1)}],
    [{"name": "m", "command": "x", "args": ["a" * (MODULE_ARG_MAX + 1)]}],
    [{"name": "m", "command": "x", "other": 1}],
]


@pytest.mark.parametrize(
    "value",
    [
        GOOD,
        {**GOOD, "name": ""},
        {**GOOD, "name": "x" * (NAME_MAX + 1)},
        {**GOOD, "facts": "x" * (FACTS_MAX + 1)},
        {**GOOD, "facts": 5},
        {**GOOD, "languages": []},
        {**GOOD, "languages": ["de"]},
        {**GOOD, "languages": [list[str]()]},
        {**GOOD, "languages": [dict[str, str]()]},
        {**GOOD, "extra": 1},
        *({**GOOD, "modules": modules} for modules in MODULE_CASES),
        *({**GOOD, "theme": theme} for theme in THEME_CASES),
        *({**GOOD, "privacy_url": url} for url in PRIVACY_URL_CASES),
        {"name": "A", "facts": ""},
        ["not", "an", "object"],
    ],
)
def test_the_core_accepts_exactly_what_the_schema_accepts(value: object) -> None:
    accepted = True
    try:
        parse(value)
    except SettingsRefused:
        accepted = False
    assert accepted == (not schema_errors(value)), (
        f"core and schema disagree on {value!r}"
    )


# --- choosing a source ---


def test_no_source_refuses_and_says_so() -> None:
    with pytest.raises(SettingsRefused, match="no settings source"):
        load_settings({})
    assert "refused" in describe_source({})


def test_two_sources_refuse_instead_of_guessing(tmp_path: Path) -> None:
    both = {"SETTINGS_URL": "http://x", "SETTINGS_FILE": str(tmp_path / "a.json")}
    with pytest.raises(SettingsRefused, match="only one"):
        load_settings(both)
    assert "refused" in describe_source(both)


def test_a_portal_address_needs_its_secret() -> None:
    with pytest.raises(SettingsRefused, match="missing"):
        load_settings({"SETTINGS_URL": "http://x"}, "7")


def test_a_call_that_names_no_business_is_refused_by_the_portal_and_never_asked() -> (
    None
):
    asked: list[str] = []
    with (
        fake_portal(paths=asked) as url,
        pytest.raises(SettingsRefused, match="names no Business"),
    ):
        load_settings(portal_env(url))
    assert asked == []


def test_the_eval_channels_test_business_is_valid_settings() -> None:
    got = load_settings({"SETTINGS_FILE": str(BUSINESS_FILE)})
    assert got.name == "Tandkliniken Exempel" and got.languages == ("sv", "en")
    assert not schema_errors(json.loads(BUSINESS_FILE.read_text("utf-8")))


def test_the_eval_channels_module_business_names_its_module() -> None:
    got = load_settings({"SETTINGS_FILE": str(MODULE_BUSINESS_FILE)})
    assert got.modules == (
        Module("hours", command="python", args=("-m", "modules.example")),
    )
    assert not schema_errors(json.loads(MODULE_BUSINESS_FILE.read_text("utf-8")))


def test_modules_come_through_from_the_portal() -> None:
    with fake_portal(body={**GOOD, "modules": [REMOTE, LOCAL]}) as url:
        got = load_settings(portal_env(url), "7")
    assert got.modules == (
        Module("booking", url="https://modules.example/mcp"),
        Module("hours", command="python", args=("-m", "x")),
    )


def test_the_theme_comes_through_from_the_portal() -> None:
    theme = {
        "accent": "#1a2a44",
        "accent_text": "#ffffff",
        "logo_url": "https://portal.example/logo/abc/",
    }
    with fake_portal(body={**GOOD, "theme": theme}) as url:
        got = load_settings(portal_env(url), "7")
    assert got.theme == Theme("#1a2a44", "#ffffff", "https://portal.example/logo/abc/")
    with fake_portal() as url:  # no theme: Voice's own look
        assert load_settings(portal_env(url), "7").theme == Theme()


def test_the_privacy_notice_address_comes_through_from_the_portal() -> None:
    with fake_portal(
        body={**GOOD, "privacy_url": "https://example.se/integritet"}
    ) as url:
        assert (
            load_settings(portal_env(url), "7").privacy_url
            == "https://example.se/integritet"
        )
    with fake_portal() as url:  # none given: no link
        assert load_settings(portal_env(url), "7").privacy_url is None


def test_a_missing_or_broken_file_refuses(tmp_path: Path) -> None:
    broken = tmp_path / "b.json"
    broken.write_text("{not json")
    for path in (tmp_path / "nope.json", broken):
        with pytest.raises(SettingsRefused):
            load_settings({"SETTINGS_FILE": str(path)})


# --- the Portal adapter ---


def test_a_named_business_is_the_one_asked_for_and_never_comes_from_a_file() -> None:
    asked: list[str] = []
    with fake_portal(paths=asked) as url:
        load_settings(portal_env(url), "42")  # a ticket named Business 42
    assert asked == ["/api/settings/42/"]
    with pytest.raises(SettingsRefused, match="named Business"):
        load_settings({"SETTINGS_FILE": str(BUSINESS_FILE)}, "42")
    with pytest.raises(
        SettingsRefused, match="missing"
    ):  # a ticket does not stand in for the secret
        load_settings({"SETTINGS_URL": "http://x"}, "42")


def test_the_portal_is_asked_for_the_business_with_the_secret() -> None:
    with fake_portal() as url:
        got = load_settings(portal_env(url), "7")
    assert got == Settings("Anna's Salon", "Öppet 8-17.", ("sv", "en"))


def test_a_settings_change_shows_up_in_the_next_call() -> None:
    with fake_portal() as url:
        first = load_settings(portal_env(url), "7")
    with fake_portal(body={**GOOD, "facts": "Stängt i juli."}) as url:
        second = load_settings(portal_env(url), "7")
    assert (first.facts, second.facts) == ("Öppet 8-17.", "Stängt i juli.")


def test_a_wrong_secret_a_bad_reply_or_a_down_portal_refuses() -> None:
    with fake_portal() as url, pytest.raises(SettingsRefused, match="401"):
        load_settings({**portal_env(url), "CORE_SECRET": "wrong"}, "7")
    with (
        fake_portal(body={**GOOD, "languages": []}) as url,
        pytest.raises(SettingsRefused),
    ):
        load_settings(portal_env(url), "7")
    with fake_portal(status=404) as url, pytest.raises(SettingsRefused, match="404"):
        load_settings(portal_env(url), "7")
    with fake_portal(status=302) as url, pytest.raises(SettingsRefused, match="302"):
        load_settings(
            portal_env(url), "7"
        )  # a moved Portal is refused, never followed with the secret
    with fake_portal() as url:  # the server has stopped by the time we ask
        pass
    with pytest.raises(SettingsRefused, match="no settings"):
        load_settings(portal_env(url), "7")


def test_a_business_id_that_is_not_a_number_never_reaches_a_path() -> None:
    for bad in ("..", "1/../2", "1?x=y", "-1"):
        with pytest.raises(SettingsRefused, match="not a number"):
            load_settings(portal_env("http://127.0.0.1:1"), bad)


def test_the_refusal_text_names_the_portal_host_never_a_password_in_its_address() -> (
    None
):
    env = portal_env("http://user:pw@127.0.0.1:1")
    with pytest.raises(SettingsRefused) as refused:
        load_settings(env, "7")
    assert "pw" not in str(refused.value) and "user" not in str(refused.value)


def test_a_reply_nested_too_deep_or_an_address_that_is_not_http_refuses() -> None:
    with fake_portal(body="[" * 60000) as url, pytest.raises(SettingsRefused):
        load_settings(portal_env(url), "7")
    for bad in ("file:///etc/passwd", "http//x", "ftp://x"):
        with pytest.raises(SettingsRefused, match="http"):
            load_settings(portal_env(bad), "7")


def test_a_secret_with_a_line_break_refuses_without_printing_it() -> None:
    with fake_portal() as url, pytest.raises(SettingsRefused) as refused:
        load_settings({**portal_env(url), "CORE_SECRET": "sekret\nX: y"}, "7")
    assert "sekret" not in str(refused.value)


def test_the_env_example_names_exactly_one_settings_source() -> None:
    values = {k: v or "" for k, v in dotenv_values(".env.example").items()}
    # Both would refuse every call; none too. A local run uses the Portal (the file source is for evals only).
    assert bool(values.get("SETTINGS_URL")) != bool(values.get("SETTINGS_FILE"))
    assert values.get("SETTINGS_URL") and values.get("CORE_SECRET")


def test_the_secret_never_reaches_the_refusal_text() -> None:
    with fake_portal() as url:
        pass
    with pytest.raises(SettingsRefused) as refused:
        load_settings(portal_env(url), "7")
    assert "s3cret" not in str(refused.value)


# --- the prompt built from one Business ---


def test_the_prompt_is_built_from_the_business_and_keeps_the_disclosure() -> None:
    prompt = system_instruction(parse(GOOD))
    assert f'Start every call by saying exactly: "{DISCLOSURE}"' in prompt
    assert (
        "Speak Swedish. Answer in the language the caller last spoke: Swedish or English."
        in prompt
    )
    assert prompt.endswith("Business facts:\nname: Anna's Salon\nÖppet 8-17.")


def test_a_single_language_business_is_not_told_to_switch() -> None:
    prompt = system_instruction(parse({**GOOD, "languages": ["en"]}))
    assert "Speak English." in prompt and "last spoke" not in prompt


def test_a_refused_call_says_the_disclosure_then_the_reason_and_holds_no_facts() -> (
    None
):
    prompt = refusal_instruction()
    assert DISCLOSURE in prompt and REFUSAL in prompt
    assert "Business facts" not in prompt
