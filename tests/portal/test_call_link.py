# pyright: basic
# (django-stubs types model fields for mypy's plugin; strict pyright cannot read them)
"""A Business's call link sends a page loaded in a frame to the core with a ticket for that Business only, once it has saved its website (make test-db).

The ticket is checked by the core's own code (voice/ticket.py), as in tests/portal/test_test_call.py.
"""

import base64
import hashlib
import json
import re
import time
from html import unescape
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from django.contrib.staticfiles import finders
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import Client

from portal.accounts import domain as portal_domain
from portal.accounts import theme
from portal.accounts.models import Account, Business
from tests.portal.helpers import business_with_login
from voice import ticket as core_ticket
from voice.ticket import Ticket, read_ticket

pytestmark = [pytest.mark.db, pytest.mark.django_db]

SECRET = "a-secret-for-tests"
# What a browser sends when the panel on the Business's website loads the call link.
IN_A_FRAME = {"Sec-Fetch-Dest": "iframe"}
SENTENCE = (
    "This call can't be opened from here. Start it from the company's own website."
)


def assert_the_refusal_page(page: str) -> None:
    """The refusal shows in the Call button's panel: a page with its language and the sentence as its one heading."""
    assert '<html lang="en">' in page
    heading = re.search(r"<h1[^>]*>(.*?)</h1>", page, re.DOTALL)
    assert heading and unescape(heading[1]).strip() == SENTENCE


@pytest.fixture(autouse=True)
def core(settings: Any) -> None:
    settings.CORE_SECRET = SECRET
    settings.CORE_URL = "https://voice.example.se/"
    settings.PORTAL_URL = "https://portal.example.se"


def test_the_link_sends_anyone_to_the_core_with_a_ticket_for_that_business() -> None:
    anna, _ = business_with_login("anna.testsson@example.com", "Anna's Salon")
    bo, _ = business_with_login("bo.testsson@example.com", "Bo's Bikes")
    Business.objects.filter(pk=anna.pk).update(website_domain="anna.example.se")

    response = Client().get(f"/call/{anna.call_slug}/", headers=IN_A_FRAME)  # no login

    assert response.status_code == 302
    parts = urlsplit(response["Location"])
    assert (parts.scheme, parts.netloc, parts.path) == (
        "https",
        "voice.example.se",
        "/",
    )
    ticket = parse_qs(parts.query)["ticket"][0]
    # The ticket carries the Business's own saved domain, which the core turns into the frame-ancestors header.
    assert read_ticket(ticket, SECRET) == Ticket(
        anna.pk, "call_link", "anna.example.se"
    )
    assert anna.pk != bo.pk
    assert read_ticket(ticket, SECRET, time.time() + 3600) is None


def test_a_business_with_no_saved_website_gets_no_ticket(
    caplog: pytest.LogCaptureFixture,
) -> None:
    anna, _ = business_with_login("anna.testsson@example.com", "Anna's Salon")
    assert anna.website_domain == ""

    response = Client().get(f"/call/{anna.call_slug}/", headers=IN_A_FRAME)

    assert response.status_code == 403 and "Location" not in response
    assert_the_refusal_page(response.content.decode())
    assert f"Business {anna.pk} has no website domain" in caplog.text


@pytest.mark.parametrize(
    "headers",
    [
        {},  # a pasted link in a tab on an iPhone before iOS 16.4 says nothing
        {"Sec-Fetch-Dest": "document"},  # a tab, a pasted link, a popup
        {"Sec-Fetch-Dest": "empty"},  # a script's fetch
        {"Sec-Fetch-Dest": ""},
        {"Sec-Fetch-Dest": "IFRAME"},  # the browser writes it lower case
    ],
)
def test_a_request_that_does_not_say_it_is_in_a_frame_gets_no_ticket(
    headers: dict[str, str], caplog: pytest.LogCaptureFixture
) -> None:
    anna, _ = business_with_login("anna.testsson@example.com", "Anna's Salon")
    Business.objects.filter(pk=anna.pk).update(website_domain="anna.example.se")

    response = Client().get(f"/call/{anna.call_slug}/", headers=headers)

    assert response.status_code == 403 and "Location" not in response
    assert_the_refusal_page(response.content.decode())
    assert f"Business {anna.pk} opened outside a frame" in caplog.text


def test_the_call_link_can_be_framed_but_nothing_else_of_the_portal_can() -> None:
    anna, client = business_with_login("anna.testsson@example.com", "Anna's Salon")
    Business.objects.filter(pk=anna.pk).update(website_domain="anna.example.se")

    # The panel frames the link, so Django's own refusal to be framed is lifted for it, on the refusal too.
    for headers in (IN_A_FRAME, {}):
        response = Client().get(f"/call/{anna.call_slug}/", headers=headers)
        assert "X-Frame-Options" not in response
    # Every other page still refuses (the core's frame-ancestors guards the call page itself).
    assert client.get("/dashboard/")["X-Frame-Options"] == "DENY"
    assert Client().get("/call-button.js")["X-Frame-Options"] == "DENY"


def test_the_core_and_the_portal_hold_the_same_rule_for_a_plain_hostname() -> None:
    assert core_ticket.DOMAIN_PATTERN == portal_domain.DOMAIN_PATTERN, (
        "voice/ticket.py and portal/accounts/domain.py disagree on DOMAIN_PATTERN: edit the one that changed"
    )
    assert core_ticket.DOMAIN_MAX == portal_domain.DOMAIN_MAX


def test_the_link_cannot_be_guessed_and_only_reads() -> None:
    anna, _ = business_with_login("anna.testsson@example.com", "Anna's Salon")
    assert Client().get("/call/not-a-link/").status_code == 404
    assert (
        Client().get(f"/call/{anna.pk}/").status_code == 404
    )  # the number is not the link
    assert Client().post(f"/call/{anna.call_slug}/").status_code == 405


def test_a_portal_with_no_secret_sends_nobody_to_the_core(settings: Any) -> None:
    anna, _ = business_with_login("anna.testsson@example.com", "Anna's Salon")
    Business.objects.filter(pk=anna.pk).update(website_domain="anna.example.se")
    settings.CORE_SECRET = ""
    response = Client().get(f"/call/{anna.call_slug}/", headers=IN_A_FRAME)
    assert response.status_code == 503 and "Location" not in response


def test_every_business_has_its_own_link_and_the_database_refuses_a_shared_one() -> (
    None
):
    anna, _ = business_with_login("anna.testsson@example.com", "Anna's Salon")
    bo, _ = business_with_login("bo.testsson@example.com", "Bo's Bikes")
    assert anna.call_slug != bo.call_slug and len(anna.call_slug) >= 20
    with pytest.raises(IntegrityError), transaction.atomic():
        Business.objects.filter(pk=bo.pk).update(call_slug=anna.call_slug)


def snippet(page: str) -> str:
    """The script tag on the dashboard, as the Business would paste it."""
    return unescape(page).split("<code>")[1].split("</code>")[0]


def test_the_dashboard_shows_the_script_snippet_only_with_a_saved_website() -> None:
    anna, client = business_with_login("anna.testsson@example.com", "Anna's Salon")
    bo, _ = business_with_login("bo.testsson@example.com", "Bo's Bikes")

    closed = client.get("/dashboard/").content.decode()
    assert "<code>" not in closed and "Your call button is closed" in closed
    assert anna.call_slug not in closed  # no bare call link either

    Business.objects.filter(pk=anna.pk).update(website_domain="anna.example.se")
    page = client.get("/dashboard/").content.decode()
    assert "closed" not in page
    assert snippet(page) == (
        f'<script async src="https://portal.example.se/static/portal/call-button.v1.js?business={anna.call_slug}"'
        f' data-core="https://voice.example.se" data-fill="{theme.DEEP_SEA}" data-ink="{theme.FOAM}"'
        f' integrity="{served_file_hash()}" crossorigin="anonymous"></script>'
    )
    assert bo.call_slug not in page
    assert f"/call/{anna.call_slug}/" not in page
    # the Copy button copies the code block it names, and its script is loaded
    assert (
        '<pre id="call-button-code"' in page and 'data-copy="call-button-code"' in page
    )
    assert "portal/portal.js" in page


def test_the_dashboard_names_the_addresses_a_security_policy_must_allow() -> None:
    anna, client = business_with_login("anna.testsson@example.com", "Anna's Salon")

    assert "security policy" not in client.get("/dashboard/").content.decode()

    Business.objects.filter(pk=anna.pk).update(website_domain="anna.example.se")
    page = client.get("/dashboard/").content.decode()
    # Scripts need the Portal; frames need the Portal and the core (the panel redirects from one to the other).
    assert "scripts from <code>https://portal.example.se</code>" in page
    assert (
        "frames from both <code>https://portal.example.se</code> and <code>https://voice.example.se</code>"
        in page
    )
    assert "microphone=(self)" in page
    assert snippet(page).startswith("<script")  # the new text sits after the snippet


def served_file() -> bytes:
    """The versioned script as collectstatic ships it and WhiteNoise serves it."""
    path = finders.find("portal/call-button.v1.js")
    assert isinstance(path, str), (
        "portal/static/portal/call-button.v1.js is not a static file"
    )
    with open(path, "rb") as f:
        return f.read()


def served_file_hash() -> str:
    return "sha384-" + base64.b64encode(hashlib.sha384(served_file()).digest()).decode()


def test_the_snippet_names_the_served_file_by_its_hash_and_tells_it_what_to_draw(
    settings: Any,
) -> None:
    anna, client = business_with_login("anna.testsson@example.com", "Anna's Salon")
    Business.objects.filter(pk=anna.pk).update(
        website_domain="anna.example.se", accent="#ffd60a"
    )
    tag = snippet(client.get("/dashboard/").content.decode())

    # A browser runs the file only when its bytes hash to this, and asks for it with CORS (WhiteNoise answers every origin).
    assert (
        f' integrity="{served_file_hash()}"' in tag
        and ' crossorigin="anonymous"' in tag
    )
    # The hash `make generate` wrote is the file's (`make generate-check` keeps it current).
    with open(settings.BASE_DIR / "call-button.v1.integrity") as f:
        assert f.read().strip() == served_file_hash(), (
            "portal/call-button.v1.integrity is stale: run make generate (a changed script belongs in call-button.v2.js)"
        )
    fill, ink = theme.on_accent("#ffd60a")
    assert (
        f' data-core="https://voice.example.se" data-fill="{fill}" data-ink="{ink}"'
        in tag
    )
    # WhiteNoise serves the file with the CORS header a cross-origin integrity check needs (here from the source tree, as a local run does; the image serves the collected copy).
    settings.WHITENOISE_USE_FINDERS = True
    settings.WHITENOISE_AUTOREFRESH = True
    response = Client().get(
        f"/static/portal/call-button.v1.js?business={anna.call_slug}"
    )
    assert (
        response.status_code == 200 and response["Access-Control-Allow-Origin"] == "*"
    )
    assert b"".join(response.streaming_content) == served_file()  # pyright: ignore[reportAttributeAccessIssue]  # a FileResponse streams
    # The file reads those attributes and writes nothing of its own in.
    script = served_file().decode()
    assert "tag.dataset.core" in script and "{ fill, ink } = tag.dataset" in script
    assert "{{" not in script


def test_the_script_is_served_with_the_core_it_lets_the_microphone_into() -> None:
    response = Client().get(
        "/call-button.js"
    )  # no login: the Business's website loads it, with a tag pasted before VOI-135

    assert response.status_code == 200
    assert response["Content-Type"] == "text/javascript; charset=utf-8"
    script = response.content.decode()
    assert '"https://voice.example.se"' in script  # CORE_URL's origin, no path
    # The old route writes the tag's attributes in front of the very file a new tag names.
    assert response.content.endswith(served_file())
    # The launcher's words are Swedish on any host page, so a screen reader is told so (WCAG 3.1.2).
    assert 'launcher.lang = "sv"' in script and 'panel.lang = "sv"' in script
    assert Client().post("/call-button.js").status_code == 405


def test_the_snippet_and_the_script_agree_on_the_tag_and_the_route() -> None:
    anna, client = business_with_login("anna.testsson@example.com", "Anna's Salon")
    Business.objects.filter(pk=anna.pk).update(website_domain="anna.example.se")

    tag = snippet(client.get("/dashboard/").content.decode())
    script = Client().get("/call-button.js").content.decode()

    # The loader finds its Business in the query its own address carries, and opens the route the Portal serves.
    assert re.search(r'src="[^"]+\?business=[^"]+"', tag)
    assert 'searchParams.get("business")' in script
    assert "{portal}/call/${encodeURIComponent(business)}/" in script
    assert (
        Client().get(f"/call/{anna.call_slug}/", headers=IN_A_FRAME).status_code == 302
    )


def launcher_colours(script: str) -> tuple[str, str]:
    """The fill and the ink the Portal wrote onto the tag in front of the script."""
    written = re.search(
        r"Object\.assign\(document\.currentScript\?\.dataset \?\? \{\}, (\{.*\})\);",
        script,
    )
    assert written, (
        "the old route no longer writes the tag's attributes: edit launcher_colours"
    )
    data = json.loads(written[1])
    return data["fill"], data["ink"]


def test_the_launcher_carries_its_business_s_adjusted_accent_or_voice_s_own_look() -> (
    None
):
    anna, _ = business_with_login("anna.testsson@example.com", "Anna's Salon")
    bo, _ = business_with_login("bo.testsson@example.com", "Bo's Bikes")
    # #2f6b4f passes AA under Foam and stays; #ffd60a is lightened toward Deep sea text only as far as it must.
    Business.objects.filter(pk=anna.pk).update(accent="#2f6b4f")
    Business.objects.filter(pk=bo.pk).update(accent="#ffd60a")

    def served(query: str) -> tuple[str, str]:
        return launcher_colours(
            Client().get(f"/call-button.js{query}").content.decode()
        )

    assert served(f"?business={anna.call_slug}") == theme.on_accent("#2f6b4f")
    assert served(f"?business={bo.call_slug}") == theme.on_accent("#ffd60a")
    # The ring and the words on the fill reach 3:1 and 4.5:1 for every Business.
    for fill, ink in (
        served(f"?business={anna.call_slug}"),
        served(f"?business={bo.call_slug}"),
    ):
        assert theme.contrast(fill, ink) >= theme.AA_CONTRAST
    # No accent, an unknown slug, or an old tag with no query: Voice's own Deep sea and Foam.
    Business.objects.filter(pk=anna.pk).update(accent="")
    for query in (f"?business={anna.call_slug}", "?business=not-a-link", ""):
        assert served(query) == (theme.DEEP_SEA, theme.FOAM)


def test_the_script_sends_no_message_to_every_site() -> None:
    script = Client().get("/call-button.js").content.decode()
    assert "postMessage" not in script, (
        "a message between the page and the panel must name its target origin and check the sender's: add that check and edit this test"
    )


def test_a_business_cannot_set_its_own_link_from_the_settings_page() -> None:
    anna, client = business_with_login("anna.testsson@example.com", "Anna's Salon")
    client.post(
        "/settings/",
        {"name": "Anna's Salon", "facts": "", "languages": ["sv"], "call_slug": "mine"},
    )
    anna.refresh_from_db()
    assert anna.call_slug != "mine"


@pytest.mark.django_db(transaction=True)
def test_businesses_that_exist_before_the_link_each_get_their_own() -> None:
    executor = MigrationExecutor(connection)
    before = [("accounts", "0004_module_limit")]
    executor.migrate(before)
    old = executor.loader.project_state(before).apps
    for n in range(3):
        account = old.get_model("accounts", "Account").objects.create(
            email=f"old{n}@example.com"
        )
        old.get_model("accounts", "Business").objects.create(
            account=account, name=f"Old {n}"
        )

    executor = MigrationExecutor(connection)
    executor.migrate(executor.loader.graph.leaf_nodes())

    slugs = list(Business.objects.values_list("call_slug", flat=True))
    assert len(slugs) == 3 and len(set(slugs)) == 3 and all(slugs)
    assert Account.objects.count() == 3
