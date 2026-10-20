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
from datetime import datetime, timedelta
from datetime import time as clock
from decimal import Decimal
from html import unescape
from typing import Any
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

import pytest
from django.conf import settings as django_settings
from django.contrib.staticfiles import finders
from django.db import IntegrityError, transaction
from django.test import Client
from django.utils import timezone

from portal.accounts import domain as portal_domain
from portal.accounts import theme
from portal.accounts.models import BUDGET_COUNTED, CALL_KINDS, Business
from portal.accounts.views import WORST_CASE_USD_PER_SECOND
from tests.portal.helpers import a_call, business_with_login
from voice import ticket as core_ticket
from voice.cost import STORED_PRICES
from voice.serve import MAX_CALL_SECS
from voice.ticket import Ticket, read_ticket

pytestmark = [pytest.mark.db, pytest.mark.django_db]

SECRET = "a-secret-for-tests"
# What a browser sends when the panel on the Business's website loads the call link.
IN_A_FRAME = {"Sec-Fetch-Dest": "iframe"}
SENTENCE = (
    "This call can't be opened from here. Start it from the company's own website."
)
BUDGET_SPENT = "Something went wrong. We can't take calls right now."


def assert_the_refusal_page(page: str, sentence: str = SENTENCE) -> None:
    """The refusal shows in the Call button's panel: a page with its language and the sentence as its one heading."""
    assert '<html lang="en">' in page
    heading = re.search(r"<h1[^>]*>(.*?)</h1>", page, re.DOTALL)
    assert heading and unescape(heading[1]).strip() == sentence


def a_business_with_a_budget(usd: str) -> Business:
    nth = Business.objects.count() + 1
    business, _ = business_with_login(f"user-a{nth}@example.com", "Owner A's Salon")
    Business.objects.filter(pk=business.pk).update(
        website_domain="site-a.example.se", daily_budget_usd=usd
    )
    return business


def link(business: Business) -> Any:
    return Client().get(f"/call/{business.call_slug}/", headers=IN_A_FRAME)


@pytest.fixture(autouse=True)
def core(settings: Any) -> None:
    settings.CORE_SECRET = SECRET
    settings.CORE_URL = "https://voice.example.se/"
    settings.PORTAL_URL = "https://portal.example.se"


def test_the_link_sends_anyone_to_the_core_with_a_ticket_for_that_business() -> None:
    business_a, _ = business_with_login("user-a@example.com", "Owner A's Salon")
    business_b, _ = business_with_login("user-b@example.com", "Owner B's Bikes")
    Business.objects.filter(pk=business_a.pk).update(website_domain="site-a.example.se")

    response = Client().get(
        f"/call/{business_a.call_slug}/", headers=IN_A_FRAME
    )  # no login

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
        business_a.pk, "call_link", "site-a.example.se"
    )
    assert business_a.pk != business_b.pk
    assert read_ticket(ticket, SECRET, time.time() + 3600) is None


def test_a_business_with_no_saved_website_gets_no_ticket(
    caplog: pytest.LogCaptureFixture,
) -> None:
    business_a, _ = business_with_login("user-a@example.com", "Owner A's Salon")
    assert business_a.website_domain == ""

    response = Client().get(f"/call/{business_a.call_slug}/", headers=IN_A_FRAME)

    assert response.status_code == 403 and "Location" not in response
    assert_the_refusal_page(response.content.decode())
    assert f"Business {business_a.pk} has no website domain" in caplog.text


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
    business_a, _ = business_with_login("user-a@example.com", "Owner A's Salon")
    Business.objects.filter(pk=business_a.pk).update(website_domain="site-a.example.se")

    response = Client().get(f"/call/{business_a.call_slug}/", headers=headers)

    assert response.status_code == 403 and "Location" not in response
    assert_the_refusal_page(response.content.decode())
    assert f"Business {business_a.pk} opened outside a frame" in caplog.text


def test_the_call_link_can_be_framed_but_nothing_else_of_the_portal_can() -> None:
    business_a, client = business_with_login("user-a@example.com", "Owner A's Salon")
    Business.objects.filter(pk=business_a.pk).update(website_domain="site-a.example.se")

    # The panel frames the link, so Django's own refusal to be framed is lifted for it, on the refusal too.
    for headers in (IN_A_FRAME, {}):
        response = Client().get(f"/call/{business_a.call_slug}/", headers=headers)
        assert "X-Frame-Options" not in response
    # Every other page still refuses (the core's frame-ancestors guards the call page itself).
    assert client.get("/dashboard/")["X-Frame-Options"] == "DENY"
    assert Client().get("/call-button.js")["X-Frame-Options"] == "DENY"


def test_a_spent_daily_budget_refuses_with_no_ticket(
    caplog: pytest.LogCaptureFixture,
) -> None:
    business_a = a_business_with_a_budget("1.00")
    now = timezone.now()
    a_call(business_a, "priced-000000001", now, cost_usd="0.40")
    assert link(business_a).status_code == 302  # under

    a_call(business_a, "priced-000000002", now, cost_usd="0.60")  # at
    response = link(business_a)

    assert response.status_code == 403 and "Location" not in response
    assert_the_refusal_page(response.content.decode(), BUDGET_SPENT)
    assert f"Business {business_a.pk} has spent its daily budget" in caplog.text
    assert "0.6" not in caplog.text and "1.0" not in caplog.text  # the id only
    a_call(business_a, "priced-000000003", now, cost_usd="5")  # over
    assert link(business_a).status_code == 403
    business_b = a_business_with_a_budget("0")  # no records: the off switch
    assert link(business_b).status_code == 403


def test_the_demo_business_mints_a_demo_ticket_each_time_the_panel_opens(
    settings: Any, caplog: pytest.LogCaptureFixture
) -> None:
    """VOI-244: the Business DEMO_BUSINESS_ID names mints kind demo; another Business is untouched, and the setting unset makes it a plain call link.
    Opening the panel mints a ticket, so opening and closing it must not use up a visitor's calls (Petter, 2026-10-20: it did).
    The cap per address counts calls as they start, in the core (tests/test_serve.py)."""
    demo = a_business_with_a_budget("5.00")
    other = a_business_with_a_budget("5.00")
    settings.DEMO_BUSINESS_ID = demo.pk

    opened = [link(demo) for _ in range(5)]
    assert [r.status_code for r in opened] == [302] * 5
    ticket = parse_qs(urlsplit(opened[0]["Location"]).query)["ticket"][0]
    assert read_ticket(ticket, SECRET) == Ticket(demo.pk, "demo", "site-a.example.se")
    assert f"demo call minted: Business {demo.pk}" in caplog.text
    assert "127.0.0.1" not in caplog.text  # the address never reaches a log

    ticket = parse_qs(urlsplit(link(other)["Location"]).query)["ticket"][0]
    assert read_ticket(ticket, SECRET) == Ticket(
        other.pk, "call_link", "site-a.example.se"
    )

    settings.DEMO_BUSINESS_ID = None
    ticket = parse_qs(urlsplit(link(demo)["Location"]).query)["ticket"][0]
    assert read_ticket(ticket, SECRET) == Ticket(
        demo.pk, "call_link", "site-a.example.se"
    )


def test_the_demo_business_takes_twenty_demo_calls_a_day_then_its_budget(
    settings: Any, caplog: pytest.LogCaptureFixture
) -> None:
    """VOI-244: the day's cap counts the demo Business's Call records of kind demo (unpriced ones too, so a pricing failure cannot lift it), before the budget; yesterday's and other kinds' records do not count."""
    demo = a_business_with_a_budget(
        "100.00"
    )  # unpriced calls count at the floor rate: well under
    settings.DEMO_BUSINESS_ID = demo.pk
    now = timezone.now()
    for n in range(19):
        a_call(
            demo,
            f"demo-{n:012d}",
            now,
            kind="demo",
            cost_usd=None,
            price_date=None,
            cost_reason="price_unavailable",
        )
    a_call(demo, "yesterday-000001", now - timedelta(days=2), kind="demo")
    a_call(demo, "link-00000000001", now, kind="call_link")
    assert link(demo).status_code == 302  # the 20th demo call of the day

    a_call(demo, "demo-000000000019", now, kind="demo")
    refused = link(demo)
    assert refused.status_code == 403
    assert_the_refusal_page(refused.content.decode(), BUDGET_SPENT)
    assert f"call refused: Business {demo.pk} demo cap per_day" in caplog.text

    # Under the day's cap but over the budget: the budget refuses (a Call record is never deleted, so a second demo Business).
    spent = a_business_with_a_budget("1.00")
    settings.DEMO_BUSINESS_ID = spent.pk
    a_call(spent, "pricey-000000001", now, kind="demo", cost_usd="1.00")
    budget = link(spent)
    assert budget.status_code == 403
    assert f"Business {spent.pk} has spent its daily budget (kind demo)" in caplog.text
    assert f"call refused: Business {spent.pk} demo cap budget" in caplog.text
    Business.objects.filter(pk=spent.pk).update(daily_budget_usd="100.00")
    assert link(spent).status_code == 302  # budget again: a ticket


def test_a_call_with_no_cost_counts_at_the_rate_google_charged_the_priced_ones() -> (
    None
):
    business_a = a_business_with_a_budget("1.00")
    unpriced = {
        "cost_usd": None,
        "price_date": None,
        "cost_reason": "price_unavailable",
    }
    a_call(
        business_a, "unpriced-00000001", timezone.now(), length_seconds=6000, **unpriced
    )
    # 100 s for $0.50 yesterday: half a cent a second, so 99 more unpriced seconds make $0.995 today.
    a_call(
        business_a,
        "priced-000000001",
        timezone.now() - timedelta(days=1),
        length_seconds=100,
        cost_usd="0.50",
    )
    Business.objects.filter(pk=business_a.pk).update(daily_budget_usd="30.50")
    assert link(business_a).status_code == 302  # 6000 s at the rate is $30, under
    Business.objects.filter(pk=business_a.pk).update(daily_budget_usd="30.00")
    assert link(business_a).status_code == 403  # at
    # A call priced at nothing (its usage reports never came) counts like an unpriced one, not as free.
    business_b = a_business_with_a_budget("1.00")
    a_call(
        business_b,
        "priced-000000002",
        timezone.now(),
        length_seconds=100,
        cost_usd="0.50",
    )
    a_call(
        business_b, "free-00000000001", timezone.now(), length_seconds=99, cost_usd="0"
    )
    assert link(business_b).status_code == 302  # $0.995
    a_call(
        business_b, "free-00000000002", timezone.now(), length_seconds=1, cost_usd="0"
    )
    assert link(business_b).status_code == 403  # $1.00
    # A rate that does not terminate ($1.00 over 300 s) still lands exactly on the budget.
    cem = a_business_with_a_budget("2.00")
    a_call(cem, "priced-000000003", timezone.now(), length_seconds=300, cost_usd="1.00")
    a_call(cem, "unpriced-00000003", timezone.now(), length_seconds=300, **unpriced)
    assert link(cem).status_code == 403


def test_an_unpriced_call_counts_at_least_at_googles_rate_for_a_full_call(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """VOI-216: with no priced call yet, or one priced near $0, unpriced seconds still count at $0.001875 a second."""
    unpriced = {
        "cost_usd": None,
        "price_date": None,
        "cost_reason": "price_unavailable",
    }
    business_a = a_business_with_a_budget("1.00")
    a_call(
        business_a, "unpriced-00000001", timezone.now(), length_seconds=533, **unpriced
    )
    assert link(business_a).status_code == 302  # $0.999375
    a_call(
        business_a, "unpriced-00000002", timezone.now(), length_seconds=1, **unpriced
    )
    assert link(business_a).status_code == 403  # $1.00125
    assert f"Business {business_a.pk} has unpriced seconds today" in caplog.text
    business_b = a_business_with_a_budget("1.00")
    a_call(
        business_b,
        "priced-000000001",
        timezone.now() - timedelta(days=1),
        length_seconds=600,
        cost_usd="0.00000100",
    )
    a_call(
        business_b, "unpriced-00000003", timezone.now(), length_seconds=534, **unpriced
    )
    assert link(business_b).status_code == 403  # the floor, not $0.00000089


def test_the_worst_case_rate_is_googles_official_rate_for_a_full_call() -> None:
    """Parity: the Portal's rate (portal/accounts/views.py) against the stored official rates (voice/prices.json) over the core's longest call.

    The call model is docs/research/demo-call-button.md § 2: 1,600 audio tokens a minute, a turn every 15 s that re-bills the call
    so far as input audio plus a 1,500-token text prompt, and the agent speaking half the call."""
    per_m = {
        k: Decimal(str(v))
        for k, v in json.loads(STORED_PRICES.read_text())[
            "usd_per_million_tokens"
        ].items()
    }
    turns = MAX_CALL_SECS // 15
    audio_per_turn = 1600 * 15 // 60
    input_audio = audio_per_turn * turns * (turns + 1) // 2
    text_in = 1500 * turns
    output_audio = 1600 * MAX_CALL_SECS // 60 // 2
    usd = (
        input_audio * per_m["audio_in"]
        + text_in * per_m["text_in"]
        + output_audio * per_m["audio_out"]
    ) / 10**6
    assert WORST_CASE_USD_PER_SECOND == usd / MAX_CALL_SECS, (
        f"set WORST_CASE_USD_PER_SECOND in portal/accounts/views.py to {usd / MAX_CALL_SECS}"
    )


def test_a_test_call_neither_counts_nor_is_refused() -> None:
    business_a = a_business_with_a_budget("1.00")
    client = Client()
    client.force_login(business_a.account)
    a_call(business_a, "test-00000000001", timezone.now(), kind="test", cost_usd="5")
    assert link(business_a).status_code == 302
    a_call(business_a, "priced-000000001", timezone.now(), cost_usd="1")
    assert link(business_a).status_code == 403
    assert client.post("/test-call/").status_code == 302


def test_the_mint_refuses_every_counted_kind_once_the_budget_is_spent(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The refusal lives where every ticket is minted, so a counted kind from a view other than the call link is refused too, and an exempt one is not (VOI-172). The test call stands in for a future counted kind."""
    business_a = a_business_with_a_budget("1.00")
    client = Client()
    client.force_login(business_a.account)
    a_call(business_a, "priced-000000001", timezone.now(), cost_usd="1")  # at
    assert client.post("/test-call/").status_code == 302  # exempt

    monkeypatch.setitem(BUDGET_COUNTED, "test", True)
    response = client.post("/test-call/")

    assert response.status_code == 403 and "Location" not in response
    assert_the_refusal_page(response.content.decode(), BUDGET_SPENT)
    assert (
        f"Business {business_a.pk} has spent its daily budget (kind test)"
        in caplog.text
    )


def test_every_call_kind_is_counted_toward_the_budget_or_named_exempt() -> None:
    """A kind added to CALL_KINDS with no mark would never count toward the daily budget, so its calls would spend uncapped (VOI-166)."""
    assert set(BUDGET_COUNTED) == set(CALL_KINDS), (
        "mark each kind of CALL_KINDS in BUDGET_COUNTED (portal/accounts/models.py): True counts toward the daily budget, False is exempt"
    )


def test_the_day_is_counted_on_the_portal_clock(settings: Any) -> None:
    settings.TIME_ZONE = "Europe/Stockholm"
    business_a = a_business_with_a_budget("1.00")
    zone = ZoneInfo(settings.TIME_ZONE)
    midnight = datetime.combine(datetime.now(zone).date(), clock.min, tzinfo=zone)
    a_call(
        business_a, "yesterday-000001", midnight - timedelta(minutes=1), cost_usd="1"
    )
    assert link(business_a).status_code == 302
    a_call(
        business_a, "today-0000000001", midnight + timedelta(minutes=1), cost_usd="1"
    )
    assert link(business_a).status_code == 403


def test_every_business_starts_with_the_default_budget_and_the_database_refuses_a_negative_one() -> (
    None
):
    business_a, _ = business_with_login("user-a@example.com", "Owner A's Salon")
    business_a.refresh_from_db()
    assert business_a.daily_budget_usd == 10
    with pytest.raises(IntegrityError), transaction.atomic():
        Business.objects.filter(pk=business_a.pk).update(daily_budget_usd="-0.01")


def test_the_core_and_the_portal_hold_the_same_rule_for_a_plain_hostname() -> None:
    assert core_ticket.DOMAIN_PATTERN == portal_domain.DOMAIN_PATTERN, (
        "voice/ticket.py and portal/accounts/domain.py disagree on DOMAIN_PATTERN: edit the one that changed"
    )
    assert core_ticket.DOMAIN_MAX == portal_domain.DOMAIN_MAX


def test_the_link_cannot_be_guessed_and_only_reads() -> None:
    business_a, _ = business_with_login("user-a@example.com", "Owner A's Salon")
    assert Client().get("/call/not-a-link/").status_code == 404
    assert (
        Client().get(f"/call/{business_a.pk}/").status_code == 404
    )  # the number is not the link
    assert Client().post(f"/call/{business_a.call_slug}/").status_code == 405


def test_a_portal_with_no_secret_sends_nobody_to_the_core(settings: Any) -> None:
    business_a, _ = business_with_login("user-a@example.com", "Owner A's Salon")
    Business.objects.filter(pk=business_a.pk).update(website_domain="site-a.example.se")
    settings.CORE_SECRET = ""
    response = Client().get(f"/call/{business_a.call_slug}/", headers=IN_A_FRAME)
    assert response.status_code == 503 and "Location" not in response


def test_every_business_has_its_own_link_and_the_database_refuses_a_shared_one() -> (
    None
):
    business_a, _ = business_with_login("user-a@example.com", "Owner A's Salon")
    business_b, _ = business_with_login("user-b@example.com", "Owner B's Bikes")
    assert (
        business_a.call_slug != business_b.call_slug and len(business_a.call_slug) >= 20
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        Business.objects.filter(pk=business_b.pk).update(call_slug=business_a.call_slug)


@pytest.mark.parametrize(
    "slug",
    [
        'abcdefghijklmnopqrstu"',
        "abcdefghijk lmnopqrstuv",
        "abcdefghijk<lmnopqrstuv",
        "abcdefghijklmnopqrstu",
    ],
    ids=["quote", "space", "angle bracket", "too short"],
)
def test_the_database_refuses_a_call_link_the_pasted_tag_could_not_carry(
    slug: str,
) -> None:
    business_a, _ = business_with_login("user-a@example.com", "Owner A's Salon")
    with (
        pytest.raises(
            IntegrityError, match="business_call_slug_must_be_22_to_40_url_safe_chars"
        ),
        transaction.atomic(),
    ):
        Business.objects.filter(pk=business_a.pk).update(call_slug=slug)


def snippet(page: str) -> str:
    """The script tag on the dashboard, as the Business would paste it."""
    return unescape(page).split("<code>")[1].split("</code>")[0]


def test_the_dashboard_shows_the_script_snippet_only_with_a_saved_website() -> None:
    business_a, client = business_with_login("user-a@example.com", "Owner A's Salon")
    business_b, _ = business_with_login("user-b@example.com", "Owner B's Bikes")

    closed = client.get("/dashboard/").content.decode()
    assert "<code>" not in closed and "Your call button is closed" in closed
    assert business_a.call_slug not in closed  # no bare call link either

    Business.objects.filter(pk=business_a.pk).update(website_domain="site-a.example.se")
    page = client.get("/dashboard/").content.decode()
    assert "closed" not in page
    assert snippet(page) == (
        f'<script async src="https://portal.example.se/static/portal/call-button.v2.js?business={business_a.call_slug}"'
        f' data-core="https://voice.example.se" data-fill="{theme.DEEP_SEA}" data-ink="{theme.FOAM}"'
        f' integrity="{served_file_hash()}" crossorigin="anonymous"></script>'
    )
    assert business_b.call_slug not in page
    assert f"/call/{business_a.call_slug}/" not in page
    # the Copy button copies the code block it names, and its script is loaded
    assert (
        '<pre id="call-button-code"' in page and 'data-copy="call-button-code"' in page
    )
    assert "portal/portal.js" in page


def test_the_dashboard_names_the_addresses_a_security_policy_must_allow() -> None:
    business_a, client = business_with_login("user-a@example.com", "Owner A's Salon")

    assert "security policy" not in client.get("/dashboard/").content.decode()

    Business.objects.filter(pk=business_a.pk).update(website_domain="site-a.example.se")
    page = client.get("/dashboard/").content.decode()
    # Scripts need the Portal; frames need the Portal and the core (the panel redirects from one to the other).
    assert "scripts from <code>https://portal.example.se</code>" in page
    assert (
        "frames from both <code>https://portal.example.se</code> and <code>https://voice.example.se</code>"
        in page
    )
    assert "microphone=(self)" in page
    assert snippet(page).startswith("<script")  # the new text sits after the snippet


def served_file(version: int = 2) -> bytes:
    """A versioned script as collectstatic ships it and WhiteNoise serves it: the current one by default (tags pasted before VOI-244 still name v1)."""
    path = finders.find(f"portal/call-button.v{version}.js")
    assert isinstance(path, str), (
        f"portal/static/portal/call-button.v{version}.js is not a static file"
    )
    with open(path, "rb") as f:
        return f.read()


def served_file_hash(version: int = 2) -> str:
    return (
        "sha384-"
        + base64.b64encode(hashlib.sha384(served_file(version)).digest()).decode()
    )


def test_the_snippet_names_the_served_file_by_its_hash_and_tells_it_what_to_draw() -> (
    None
):
    business_a, client = business_with_login("user-a@example.com", "Owner A's Salon")
    Business.objects.filter(pk=business_a.pk).update(
        website_domain="site-a.example.se", accent="#ffd60a"
    )
    tag = snippet(client.get("/dashboard/").content.decode())

    # A browser runs the file only when its bytes hash to this, and asks for it with CORS (WhiteNoise answers every origin).
    assert (
        f' integrity="{served_file_hash()}"' in tag
        and ' crossorigin="anonymous"' in tag
    )
    # The hash `make generate` wrote is each file's (`make generate-check` keeps it current); v1 stays for tags pasted before v2.
    for version in (1, 2):
        with open(django_settings.BASE_DIR / f"call-button.v{version}.integrity") as f:
            assert f.read().strip() == served_file_hash(version), (
                f"portal/call-button.v{version}.integrity is stale: run make generate (a changed script belongs in a new version)"
            )
    fill, ink = theme.on_accent("#ffd60a")
    assert (
        f' data-core="https://voice.example.se" data-fill="{fill}" data-ink="{ink}"'
        in tag
    )
    # WhiteNoise serves the file with the CORS header a cross-origin integrity check needs (here from the source tree, as a local run does; the image serves the collected copy).
    response = Client().get(
        f"/static/portal/call-button.v2.js?business={business_a.call_slug}"
    )
    assert (
        response.status_code == 200 and response["Access-Control-Allow-Origin"] == "*"
    )
    assert b"".join(response.streaming_content) == served_file()  # pyright: ignore[reportAttributeAccessIssue]  # a FileResponse streams
    # The file reads those attributes and writes nothing of its own in.
    script = served_file().decode()
    assert "tag.dataset.core" in script and "{ fill, ink } = tag.dataset" in script
    assert "{{" not in script


def test_the_label_is_swedish_unless_the_tag_asks_for_english() -> None:
    """VOI-244: v1 said Swedish on the English landing page. Both words are Petter's (Swedish VOI-73, English 2026-10-20)."""
    script = served_file().decode()
    assert 'sv: "Prata med vår AI-assistent", en: "Talk to our AI assistant"' in script
    assert 'const lang = tag.dataset.lang === "en" ? "en" : "sv";' in script
    assert "launcher.lang = lang;" in script and "panel.lang = lang;" in script
    assert 'const label = "Prata med vår AI-assistent";' in served_file(1).decode()


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
    business_a, client = business_with_login("user-a@example.com", "Owner A's Salon")
    Business.objects.filter(pk=business_a.pk).update(website_domain="site-a.example.se")

    tag = snippet(client.get("/dashboard/").content.decode())
    script = Client().get("/call-button.js").content.decode()

    # The loader finds its Business in the query its own address carries, and opens the route the Portal serves.
    assert re.search(r'src="[^"]+\?business=[^"]+"', tag)
    assert 'searchParams.get("business")' in script
    assert "{portal}/call/${encodeURIComponent(business)}/" in script
    assert (
        Client().get(f"/call/{business_a.call_slug}/", headers=IN_A_FRAME).status_code
        == 302
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
    business_a, _ = business_with_login("user-a@example.com", "Owner A's Salon")
    business_b, _ = business_with_login("user-b@example.com", "Owner B's Bikes")
    # #2f6b4f passes AA under Foam and stays; #ffd60a is lightened toward Deep sea text only as far as it must.
    Business.objects.filter(pk=business_a.pk).update(accent="#2f6b4f")
    Business.objects.filter(pk=business_b.pk).update(accent="#ffd60a")

    def served(query: str) -> tuple[str, str]:
        return launcher_colours(
            Client().get(f"/call-button.js{query}").content.decode()
        )

    assert served(f"?business={business_a.call_slug}") == theme.on_accent("#2f6b4f")
    assert served(f"?business={business_b.call_slug}") == theme.on_accent("#ffd60a")
    # The ring and the words on the fill reach 3:1 and 4.5:1 for every Business.
    for fill, ink in (
        served(f"?business={business_a.call_slug}"),
        served(f"?business={business_b.call_slug}"),
    ):
        assert theme.contrast(fill, ink) >= theme.AA_CONTRAST
    # No accent, an unknown slug, or an old tag with no query: Voice's own Deep sea and Foam.
    Business.objects.filter(pk=business_a.pk).update(accent="")
    for query in (f"?business={business_a.call_slug}", "?business=not-a-link", ""):
        assert served(query) == (theme.DEEP_SEA, theme.FOAM)


def test_the_script_sends_no_message_to_every_site() -> None:
    script = Client().get("/call-button.js").content.decode()
    assert "postMessage" not in script, (
        "a message between the page and the panel must name its target origin and check the sender's: add that check and edit this test"
    )


def test_a_business_cannot_set_its_own_link_or_budget_from_the_settings_page() -> None:
    business_a, client = business_with_login("user-a@example.com", "Owner A's Salon")
    client.post(
        "/settings/",
        {
            "name": "Owner A's Salon",
            "instructions": "",
            "languages": ["sv"],
            "call_slug": "mine",
            "daily_budget_usd": "999",
        },
    )
    business_a.refresh_from_db()
    assert business_a.call_slug != "mine" and business_a.daily_budget_usd == 10
