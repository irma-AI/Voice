"""A Business adds, sees and removes Modules in the Portal, and the core is told about them (make test-db). No mocks of our own code."""

import socket
import sys
import threading
import time
from contextlib import closing
from typing import Any

import pytest
from django.db import IntegrityError, connection, transaction
from django.test import Client

from portal.accounts import modules as module_rules
from portal.accounts import probe
from portal.accounts.models import Module
from tests.portal.contract import schema_errors
from tests.portal.helpers import SECRET, ask_core, business_with_login

pytestmark = [pytest.mark.db, pytest.mark.django_db]

PUBLIC = (
    "https://8.8.8.8/mcp"  # a literal public address, so the form's check needs no DNS
)
EXAMPLE = (
    f"{sys.executable} -m modules.example"  # a real local Module that offers one Action
)


@pytest.fixture(autouse=True)
def core_secret(settings: Any) -> None:
    settings.CORE_SECRET = SECRET
    settings.ALLOW_LOCAL_MODULES = False  # hosted, unless a test says it is self-hosted


def add(client: Client, name: str, address: str) -> Any:
    return client.post("/modules/", {"name": name, "address": address})


def checked(client: Client) -> str:
    """The page after the Business presses Check, which is the only time the Modules are asked."""
    response = client.post("/modules/", {"check": "1"})
    assert response.status_code == 200
    return response.content.decode()


def refused(client: Client, name: str, address: str) -> str:
    response = add(client, name, address)
    assert response.status_code == 200, (name, address)
    return response.content.decode()


def test_several_modules_can_be_added_and_the_core_is_told_about_all_of_them() -> None:
    business, client = business_with_login("anna.testsson@example.com", "Anna's Salon")
    assert add(client, "bookings", PUBLIC)["Location"] == "/modules/"
    assert add(client, "hours", "https://1.1.1.1/hours/mcp")["Location"] == "/modules/"

    settings_told = ask_core(business.pk).json()
    assert settings_told["modules"] == [
        {"name": "bookings", "url": PUBLIC},
        {"name": "hours", "url": "https://1.1.1.1/hours/mcp"},
    ]
    assert not schema_errors(settings_told)
    page = client.get("/modules/").content.decode()
    assert "bookings" in page and "hours" in page


def test_a_business_with_no_modules_is_told_an_empty_list() -> None:
    business, _ = business_with_login("anna.testsson@example.com", "Anna's Salon")
    assert ask_core(business.pk).json()["modules"] == []


def test_hosted_refuses_what_could_reach_our_network_or_hold_a_password() -> None:
    _, client = business_with_login("anna.testsson@example.com", "Anna's Salon")
    for address in (
        "http://8.8.8.8/mcp",  # not https
        "https://127.0.0.1/mcp",  # this machine
        "https://10.1.2.3/mcp",  # a private network
        "https://169.254.169.254/latest/meta-data",  # the cloud's metadata address
        "https://user:secret@8.8.8.8/mcp",  # a password in the address
        "https://8.8.8.8/mcp?key=secret",  # a key in the address
        "python -m modules.example",  # a local Module
        "no-such-scheme",
    ):
        refused(client, "bad", address)
    assert not Module.objects.exists()


def test_a_local_module_is_refused_by_the_settings_check_itself_not_only_by_the_form(
    settings: Any,
) -> None:
    business, _ = business_with_login("anna.testsson@example.com", "Anna's Salon")
    Module.objects.create(
        business=business, name="sneaky", command="python", args=["-m", "x"]
    )
    Module.objects.create(business=business, name="ok", url=PUBLIC)

    assert ask_core(business.pk).json()["modules"] == [{"name": "ok", "url": PUBLIC}]
    settings.ALLOW_LOCAL_MODULES = True  # self-hosting serves it
    assert ask_core(business.pk).json()["modules"] == [
        {"name": "sneaky", "command": "python", "args": ["-m", "x"]},
        {"name": "ok", "url": PUBLIC},
    ]


def test_a_self_hosted_portal_accepts_a_local_module_and_a_plain_http_address(
    settings: Any,
) -> None:
    settings.ALLOW_LOCAL_MODULES = True
    business, client = business_with_login("anna.testsson@example.com", "Anna's Salon")
    add(client, "local", "python -m modules.example --port '8 8'")
    add(client, "mine", "http://127.0.0.1:9000/mcp")

    assert ask_core(business.pk).json()["modules"] == [
        {
            "name": "local",
            "command": "python",
            "args": ["-m", "modules.example", "--port", "8 8"],
        },
        {"name": "mine", "url": "http://127.0.0.1:9000/mcp"},
    ]
    assert not schema_errors(ask_core(business.pk).json())
    refused(client, "pw", "http://u:secret@127.0.0.1:9000/mcp")  # even here


def test_the_page_lists_the_actions_a_module_offers(settings: Any) -> None:
    settings.ALLOW_LOCAL_MODULES = True
    _, client = business_with_login("anna.testsson@example.com", "Anna's Salon")
    add(client, "hours", EXAMPLE)
    page = checked(client)
    assert "opening_hours" in page and "cannot be used" not in page


def closed_port() -> int:
    with closing(socket.socket()) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_opening_the_page_does_not_ask_the_modules(settings: Any) -> None:
    settings.ALLOW_LOCAL_MODULES = True
    _, client = business_with_login("anna.testsson@example.com", "Anna's Salon")
    with closing(socket.socket()) as listening:
        listening.bind(("127.0.0.1", 0))
        listening.listen()
        listening.setblocking(False)
        add(client, "mine", f"http://127.0.0.1:{listening.getsockname()[1]}/mcp")
        page = client.get("/modules/").content.decode()
        with pytest.raises(BlockingIOError):  # nothing connected to it
            listening.accept()
    assert "Not checked yet" in page and "mine" in page


def test_a_module_that_cannot_be_reached_says_so_and_the_others_still_show(
    settings: Any,
) -> None:
    settings.ALLOW_LOCAL_MODULES = True
    _, client = business_with_login("anna.testsson@example.com", "Anna's Salon")
    add(client, "dead", f"http://127.0.0.1:{closed_port()}/mcp")
    add(client, "missing", "no-such-program-voice")
    add(client, "hours", EXAMPLE)
    page = checked(client)
    assert page.count("cannot be used on a call right now") == 2
    assert "opening_hours" in page


def test_a_module_that_never_answers_says_so(settings: Any) -> None:
    settings.ALLOW_LOCAL_MODULES = True
    _, client = business_with_login("anna.testsson@example.com", "Anna's Salon")
    with closing(socket.socket()) as hung:
        hung.bind(("127.0.0.1", 0))
        hung.listen()
        add(client, "hung", f"http://127.0.0.1:{hung.getsockname()[1]}/mcp")
        page = checked(client)
    assert f"did not answer within {probe.PROBE_TIMEOUT_S} seconds" in page


def test_a_module_whose_address_lookup_hangs_gives_up_within_the_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    business, client = business_with_login("anna.testsson@example.com", "Anna's Salon")
    Module.objects.create(
        business=business, name="slow", url="https://slow.example/mcp"
    )
    # the resolver, standing in for a DNS server that never answers
    release = threading.Event()

    def never_answers(*_: Any, **__: Any) -> list[Any]:
        release.wait(30)
        return []

    monkeypatch.setattr(socket, "getaddrinfo", never_answers)
    started = time.monotonic()
    try:
        page = checked(client)
        took = time.monotonic() - started
    finally:
        release.set()
    assert f"did not answer within {probe.PROBE_TIMEOUT_S} seconds" in page
    assert took < probe.PROBE_TIMEOUT_S + 1


def test_a_hosted_page_does_not_reach_into_our_network_for_a_stored_address() -> None:
    business, client = business_with_login("anna.testsson@example.com", "Anna's Salon")
    Module.objects.create(
        business=business, name="inside", url="https://127.0.0.1:1/mcp"
    )
    assert "not on the public internet" in checked(client)


def test_a_module_can_be_removed_and_swapped() -> None:
    business, client = business_with_login("anna.testsson@example.com", "Anna's Salon")
    add(client, "old", PUBLIC)
    old = Module.objects.get(name="old")
    assert client.post(f"/modules/{old.pk}/remove/")["Location"] == "/modules/"
    add(client, "new", "https://1.1.1.1/mcp")
    assert ask_core(business.pk).json()["modules"] == [
        {"name": "new", "url": "https://1.1.1.1/mcp"}
    ]


def test_a_business_sees_and_removes_only_its_own_modules() -> None:
    anna, anna_client = business_with_login("anna.testsson@example.com", "Anna's Salon")
    _, bo_client = business_with_login("bo.testsson@example.com", "Bo's Bikes")
    add(anna_client, "annas", PUBLIC)
    theirs = Module.objects.get(name="annas")

    assert "annas" not in bo_client.get("/modules/").content.decode()
    assert bo_client.post(f"/modules/{theirs.pk}/remove/").status_code == 404
    assert Module.objects.filter(pk=theirs.pk).exists()
    assert ask_core(anna.pk).json()["modules"] == [{"name": "annas", "url": PUBLIC}]


def test_a_removal_must_be_a_post_behind_the_login() -> None:
    business, client = business_with_login("anna.testsson@example.com", "Anna's Salon")
    module = Module.objects.create(business=business, name="a", url=PUBLIC)
    # A link removes nothing; it goes back to the Modules page (where a login after an ended session lands).
    assert client.get(f"/modules/{module.pk}/remove/")["Location"] == "/modules/"
    assert (
        Client().post(f"/modules/{module.pk}/remove/")["Location"].startswith("/login/")
    )
    assert Module.objects.filter(pk=module.pk).exists()


def test_the_form_refuses_a_repeated_name() -> None:
    _, client = business_with_login("anna.testsson@example.com", "Anna's Salon")
    add(client, "bookings", PUBLIC)
    assert "already have a Module with that name" in refused(
        client, "bookings", "https://1.1.1.1/mcp"
    )
    assert Module.objects.count() == 1


def test_the_page_stops_offering_the_form_at_ten_and_the_post_adds_none() -> None:
    business, client = business_with_login("anna.testsson@example.com", "Anna's Salon")
    for i in range(module_rules.MODULES_MAX):
        Module.objects.create(
            business=business, name=f"m{i}", url=f"https://8.8.8.8/{i}"
        )
    assert (
        "most Modules a Business can have" in client.get("/modules/").content.decode()
    )
    assert "at most 10 Modules" in refused(client, "eleven", PUBLIC)
    assert Module.objects.count() == module_rules.MODULES_MAX


def test_the_database_refuses_a_bad_module_whoever_writes_it() -> None:
    business, _ = business_with_login("anna.testsson@example.com", "Anna's Salon")
    good: dict[str, Any] = {"business": business, "name": "a", "url": PUBLIC}
    Module.objects.create(**good)
    bad: list[dict[str, Any]] = [
        {**good, "name": "b", "url": "", "command": ""},  # no address
        {**good, "name": "b", "command": "python"},  # both
        {**good, "name": "b", "url": "", "command": "python", "args": ["x"] * 21},
        {**good, "name": "b", "url": "https://u:pw@8.8.8.8/"},  # a password
        {**good, "name": "b", "url": "https://8.8.8.8/?key=k"},  # a key
        {**good, "name": "b", "url": "ftp://8.8.8.8/"},
        {**good, "name": "  "},  # blank name
        {**good},  # the same name twice
    ]
    for fields in bad:
        with pytest.raises(IntegrityError), transaction.atomic():
            Module.objects.create(**fields)
    assert Module.objects.count() == 1


def test_the_database_refuses_an_eleventh_module() -> None:
    business, _ = business_with_login("anna.testsson@example.com", "Anna's Salon")
    for i in range(module_rules.MODULES_MAX):
        Module.objects.create(
            business=business, name=f"m{i}", url=f"https://8.8.8.8/{i}"
        )
    with pytest.raises(IntegrityError, match="module_limit"), transaction.atomic():
        Module.objects.create(business=business, name="eleven", url=PUBLIC)
    other, _ = business_with_login("bo.testsson@example.com", "Bo's Bikes")
    Module.objects.create(
        business=other, name="m0", url=PUBLIC
    )  # the limit is per Business


def test_an_address_typed_with_a_capital_scheme_is_stored_in_lower_case() -> None:
    business, client = business_with_login("anna.testsson@example.com", "Anna's Salon")
    add(client, "shouted", "HTTPS://8.8.8.8/Mcp")
    assert ask_core(business.pk).json()["modules"] == [
        {"name": "shouted", "url": "https://8.8.8.8/Mcp"}
    ]


def test_the_database_refuses_removing_a_module_any_way_but_module_remove() -> None:
    business, _ = business_with_login("anna.testsson@example.com", "Anna's Salon")
    module = Module.objects.create(business=business, name="a", url=PUBLIC)
    refused = "module_is_removed_by_module_remove"
    with pytest.raises(IntegrityError, match=refused), transaction.atomic():
        module.delete()
    with (
        pytest.raises(IntegrityError, match=refused),
        transaction.atomic(),
        connection.cursor() as cursor,
    ):
        cursor.execute("DELETE FROM accounts_module")
    with pytest.raises(IntegrityError, match=refused), transaction.atomic():
        business.delete()  # a Business's CASCADE goes through no path
    with pytest.raises(IntegrityError, match=refused), transaction.atomic():
        Module.remove(Module.objects.filter(pk=module.pk))
        Module.objects.create(business=business, name="b", url=PUBLIC).delete()
    assert Module.remove(Module.objects.filter(pk=module.pk)) == 1
    assert not Module.objects.exists()
