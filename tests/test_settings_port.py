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

from tests.evals.checks import BUSINESS_FILE
from tests.portal.contract import SCHEMA, schema_errors
from voice.agent import DISCLOSURE, REFUSAL, refusal_instruction, system_instruction
from voice.settings import (
    FACTS_MAX,
    LANGUAGES,
    NAME_MAX,
    Settings,
    SettingsRefused,
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
def fake_portal(status: int = 200, body: object = GOOD) -> Generator[str]:
    """A real server that answers like the Portal's settings address: Bearer `s3cret`, or 401."""
    seen: list[str] = []

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


def portal_env(url: str) -> dict[str, str]:
    return {"PORTAL_URL": url, "CORE_SECRET": "s3cret", "BUSINESS_ID": "7"}


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
        {**GOOD, "extra": 1},
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
    both = {"PORTAL_URL": "http://x", "SETTINGS_FILE": str(tmp_path / "a.json")}
    with pytest.raises(SettingsRefused, match="only one"):
        load_settings(both)
    assert "refused" in describe_source(both)


def test_a_portal_address_needs_its_secret_and_business() -> None:
    for env in (
        {"PORTAL_URL": "http://x"},
        {"PORTAL_URL": "http://x", "CORE_SECRET": "s"},
    ):
        with pytest.raises(SettingsRefused, match="missing"):
            load_settings(env)


def test_the_eval_channels_test_business_is_valid_settings() -> None:
    got = load_settings({"SETTINGS_FILE": str(BUSINESS_FILE)})
    assert got.name == "Tandkliniken Exempel" and got.languages == ("sv", "en")
    assert not schema_errors(json.loads(BUSINESS_FILE.read_text("utf-8")))


def test_a_missing_or_broken_file_refuses(tmp_path: Path) -> None:
    broken = tmp_path / "b.json"
    broken.write_text("{not json")
    for path in (tmp_path / "nope.json", broken):
        with pytest.raises(SettingsRefused):
            load_settings({"SETTINGS_FILE": str(path)})


# --- the Portal adapter ---


def test_the_portal_is_asked_for_the_business_with_the_secret() -> None:
    with fake_portal() as url:
        got = load_settings(portal_env(url))
    assert got == Settings("Anna's Salon", "Öppet 8-17.", ("sv", "en"))


def test_a_settings_change_shows_up_in_the_next_call() -> None:
    with fake_portal() as url:
        first = load_settings(portal_env(url))
    with fake_portal(body={**GOOD, "facts": "Stängt i juli."}) as url:
        second = load_settings(portal_env(url))
    assert (first.facts, second.facts) == ("Öppet 8-17.", "Stängt i juli.")


def test_a_wrong_secret_a_bad_reply_or_a_down_portal_refuses() -> None:
    with fake_portal() as url, pytest.raises(SettingsRefused, match="401"):
        load_settings({**portal_env(url), "CORE_SECRET": "wrong"})
    with (
        fake_portal(body={**GOOD, "languages": []}) as url,
        pytest.raises(SettingsRefused),
    ):
        load_settings(portal_env(url))
    with fake_portal(status=404) as url, pytest.raises(SettingsRefused, match="404"):
        load_settings(portal_env(url))
    with fake_portal(status=302) as url, pytest.raises(SettingsRefused, match="302"):
        load_settings(
            portal_env(url)
        )  # a moved Portal is refused, never followed with the secret
    with fake_portal() as url:  # the server has stopped by the time we ask
        pass
    with pytest.raises(SettingsRefused, match="no settings"):
        load_settings(portal_env(url))


def test_the_secret_never_reaches_the_refusal_text() -> None:
    with fake_portal() as url:
        pass
    with pytest.raises(SettingsRefused) as refused:
        load_settings(portal_env(url))
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
