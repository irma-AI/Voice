"""The Portal starts only with a clear environment: a missing or contradictory value stops it instead of falling open."""

import os
import subprocess
import sys

import pytest

PRODUCTION = {
    "ENVIRONMENT": "production",
    "DJANGO_SECRET_KEY": "not-the-local-one",
    "ALLOWED_HOSTS": "portal.example.com, www.example.com",
    "PORTAL_URL": "https://portal.example.com",
    "EMAIL_HOST": "smtp.example.com",
    "EMAIL_FROM": "voice@example.com",
    "CORE_SECRET": "not-the-local-one-either",
    "CORE_URL": "https://voice.example.com",
}


def starts(**env: str) -> tuple[bool, str]:
    clean = {
        k: v
        for k, v in os.environ.items()
        if k not in {*PRODUCTION, "DEBUG", "DATABASE_URL"}
    }
    run = subprocess.run(
        [sys.executable, "-c", "import portal.settings as s; print(s.ALLOWED_HOSTS)"],
        env={**clean, **env},
        capture_output=True,
        text=True,
        check=False,
    )
    return run.returncode == 0, run.stdout + run.stderr


def test_a_complete_production_environment_starts_and_a_local_one_starts_with_debug() -> (
    None
):
    ok, out = starts(**PRODUCTION)
    assert ok, out
    assert "'www.example.com'" in out  # hosts are trimmed
    assert starts(ENVIRONMENT="local", DEBUG="1")[0]


@pytest.mark.parametrize("missing", sorted(PRODUCTION))
def test_production_refuses_to_start_without_any_one_of_its_values(
    missing: str,
) -> None:
    ok, out = starts(**{k: v for k, v in PRODUCTION.items() if k != missing})
    assert not ok and "ImproperlyConfigured" in out


def test_the_core_address_must_be_https_in_production() -> None:
    assert not starts(**{**PRODUCTION, "CORE_URL": "http://voice.example.com"})[0]


def test_debug_is_refused_in_production_and_without_an_environment() -> None:
    assert not starts(**PRODUCTION, DEBUG="1")[0]
    assert not starts(DEBUG="1")[0]  # DEBUG alone must not pass for a local run
    assert not starts(ENVIRONMENT="staging", DEBUG="1")[
        0
    ]  # the environment is a closed set


def test_the_time_zone_defaults_to_utc_and_a_name_that_is_not_one_stops_the_portal() -> (
    None
):
    local = {"ENVIRONMENT": "local", "DEBUG": "1"}
    for env, want in (
        ({}, "UTC"),
        ({"TIME_ZONE": "Europe/Stockholm"}, "Europe/Stockholm"),
    ):
        run = subprocess.run(
            [sys.executable, "-c", "import portal.settings as s; print(s.TIME_ZONE)"],
            env={**os.environ, **local, **env},
            capture_output=True,
            text=True,
            check=False,
        )
        assert run.stdout.strip() == want, run.stderr
    assert not starts(**local, TIME_ZONE="Nowhere/Atlantis")[0]
