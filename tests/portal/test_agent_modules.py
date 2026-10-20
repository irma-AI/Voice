"""A Business's assistant lists, checks and adds its Modules through the agent endpoint, by the Modules page's own rules (VOI-114, make test-db).

The Commands run on the SDK's worker threads with their own database connection, so these tests commit (transaction=True).
"""

# pyright: basic
# (django-stubs types model fields for mypy's plugin; strict pyright cannot read them)

import html
import socket
import time
from contextlib import closing
from typing import Any

import pytest
from django.test import Client

from portal.accounts import modules as module_rules
from portal.accounts import probe
from portal.accounts.models import Business, CommandRecord, Module
from tests.portal.helpers import business_with_login
from tests.portal.test_agent_endpoint import a_token, ask
from tests.portal.test_modules_page import EXAMPLE, PUBLIC, closed_port

pytestmark = [pytest.mark.db, pytest.mark.django_db(transaction=True)]


@pytest.fixture(autouse=True)
def hosted(settings: Any) -> None:
    settings.ALLOW_LOCAL_MODULES = False  # hosted, unless a test says it is self-hosted


def run(secret: str, command: str, **arguments: Any) -> dict[str, Any]:
    answer = ask("tools/call", {"name": command, "arguments": arguments}, secret)
    assert answer.status_code == 200, answer.content
    return answer.json()["result"]


def text(answer: dict[str, Any]) -> str:
    return answer["content"][0]["text"]


def stored(business: Business) -> list[tuple[str, str, str, list[str]]]:
    return [
        (m.name, m.url, m.command, m.args)
        for m in Module.objects.filter(business=business).order_by("id")
    ]


def two_businesses() -> tuple[tuple[Business, Client], tuple[Business, str]]:
    """Two Businesses alike: one adds through the page, the other through the Commands."""
    page, client = business_with_login("user-a@example.com", "Owner's Salon")
    agent, _ = business_with_login("user-b@example.com", "Owner's Salon")
    return (page, client), (agent, a_token(agent, "full"))


def page_add(client: Client, name: str, address: str) -> str:
    """The Modules page's own Add: "" once added, else the page with its refusal."""
    answer = client.post("/modules/", {"name": name, "address": address})
    return "" if answer.status_code == 302 else html.unescape(answer.content.decode())


# Each is given to both; the first Module, "Bookings", is added to both first.
ADDS = [
    ("Hours", PUBLIC),
    ("Bookings", "https://8.8.4.4/mcp"),  # a name taken
    ("Pw", "https://user:secret@8.8.8.8/mcp"),  # a password in the address
    ("Key", "https://8.8.8.8/mcp?key=1"),
    ("Plain", "http://8.8.8.8/mcp"),  # not https on the hosted service
    ("Inside", "https://127.0.0.1/mcp"),  # not on the public internet
    ("Local", "python -m modules.example"),  # local only when self-hosted
    ("  ", PUBLIC),
    ("Empty", ""),
]


@pytest.mark.parametrize(("name", "address"), ADDS)
def test_adding_stores_and_refuses_the_same_as_the_modules_page(
    name: str, address: str
) -> None:
    (page, client), (agent, secret) = two_businesses()
    assert page_add(client, "Bookings", PUBLIC) == ""
    assert not run(secret, "add_module", name="Bookings", address=PUBLIC).get("isError")
    refused = page_add(client, name, address)
    answer = run(secret, "add_module", name=name, address=address)
    assert stored(agent) == stored(page)
    assert bool(answer.get("isError")) == bool(refused)
    if refused:
        assert text(answer) in refused  # the page's own sentence
    assert CommandRecord.objects.filter(command="add_module").last().result == "done"


def test_an_eleventh_module_is_refused_by_the_databases_limit_as_on_the_page() -> None:
    (page, client), (agent, secret) = two_businesses()
    for i in range(module_rules.MODULES_MAX):
        for business in (page, agent):
            Module.objects.create(business=business, name=f"m{i}", url=PUBLIC)
    refused = page_add(client, "One more", PUBLIC)
    answer = run(secret, "add_module", name="One more", address=PUBLIC)
    assert answer.get("isError") and refused and text(answer) in refused
    assert len(stored(agent)) == module_rules.MODULES_MAX


def test_listing_shows_the_tokens_own_modules_and_asks_none_of_them(
    settings: Any,
) -> None:
    settings.ALLOW_LOCAL_MODULES = True
    (other, _), (business, _) = two_businesses()
    Module.objects.create(business=other, name="Theirs", url=PUBLIC)
    with closing(socket.socket()) as listening:
        listening.bind(("127.0.0.1", 0))
        listening.listen()
        listening.setblocking(False)
        address = f"http://127.0.0.1:{listening.getsockname()[1]}/mcp"
        Module.objects.create(business=business, name="Mine", url=address)
        Module.objects.create(
            business=business,
            name="Hours",
            command="python",
            args=["-m", "modules.example"],
        )
        listed = run(a_token(business, "read"), "list_modules")["structuredContent"]
        with pytest.raises(BlockingIOError):  # nothing connected to it
            listening.accept()
    assert listed["result"] == [
        {"name": "Mine", "address": address},
        {"name": "Hours", "address": "python -m modules.example"},
    ]


def test_checking_a_module_lists_its_actions(settings: Any) -> None:
    settings.ALLOW_LOCAL_MODULES = True
    _, (business, _) = two_businesses()
    secret = a_token(business, "read")
    Module.objects.create(
        business=business,
        name="Hours",
        command=EXAMPLE.split()[0],
        args=EXAMPLE.split()[1:],
    )
    answer = run(secret, "check_module", name="Hours")["structuredContent"]
    assert answer["problem"] is None
    assert [a["name"] for a in answer["actions"]] == ["opening_hours"]


def test_checking_a_dead_or_hung_module_gives_up_within_the_limit(
    settings: Any,
) -> None:
    settings.ALLOW_LOCAL_MODULES = True
    _, (business, _) = two_businesses()
    secret = a_token(business, "read")
    Module.objects.create(
        business=business, name="Dead", url=f"http://127.0.0.1:{closed_port()}/mcp"
    )
    assert (
        "could not be reached"
        in run(secret, "check_module", name="Dead")["structuredContent"]["problem"]
    )
    with closing(socket.socket()) as hung:
        hung.bind(("127.0.0.1", 0))
        hung.listen()
        Module.objects.create(
            business=business,
            name="Hung",
            url=f"http://127.0.0.1:{hung.getsockname()[1]}/mcp",
        )
        started = time.monotonic()
        answer = run(secret, "check_module", name="Hung")["structuredContent"]
        took = time.monotonic() - started
    assert f"did not answer within {probe.PROBE_TIMEOUT_S} seconds" in answer["problem"]
    assert took < probe.PROBE_TIMEOUT_S + 1


def test_another_businesss_module_answers_like_an_unknown_one() -> None:
    (other, _), (_, secret) = two_businesses()
    Module.objects.create(business=other, name="Theirs", url=PUBLIC)
    for command in ("check_module", "remove_module"):
        theirs = run(secret, command, name="Theirs")
        unknown = run(secret, command, name="Nothing")
        assert theirs.get("isError") and text(theirs) == text(unknown)
    assert Module.objects.filter(business=other).count() == 1


def test_an_add_is_recorded_without_its_values() -> None:
    _, (_, secret) = two_businesses()
    run(secret, "add_module", name="Hours", address=PUBLIC)
    rows = list(CommandRecord.objects.values())
    assert [r["command"] for r in rows] == ["add_module"]
    assert "Hours" not in str(rows) and "8.8.8.8" not in str(rows)
