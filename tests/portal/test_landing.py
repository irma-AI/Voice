"""The landing page (`home`) tells a visitor what Voice is and where to go next (make test; the logged-in check needs make test-db).

What it renders is checked through the test client, never its CSS or the animation (VOI-80 § Testing Decisions).
"""

from typing import Any

import pytest
from django.test import Client
from django.urls import reverse

from tests.portal.helpers import business_with_login

SELF_HOST = "https://github.com/irma-AI/Voice#self-host"


def landing() -> str:
    response = Client().get(reverse("home"))
    assert response.status_code == 200
    return response.content.decode()


def test_the_page_renders_its_headline_subline_and_links(settings: Any) -> None:
    settings.CONTACT_EMAIL = ""
    page = landing()
    assert "Voice for the agentic company." in page
    assert (
        "Voice answers your callers and gets things done through Modules. Connect any service that speaks MCP, and your agent can use it"
        in page
    )
    assert f'href="{reverse("login")}"' in page
    assert f'href="{SELF_HOST}"' in page and "Open code · Self-host it" in page


def test_every_use_case_carries_one_of_the_three_marks(settings: Any) -> None:
    settings.CONTACT_EMAIL = ""
    page = landing()
    uses = page.split('<li class="use">')[1:]
    assert uses, "the use cases are missing"
    marks = ("Works today", "With a Module", "Planned")
    for use in uses:
        assert sum(f">{m}</span>" in use for m in marks) == 1, (
            f"a use case needs exactly one mark: {use[:80]}"
        )
    for mark in marks:
        assert f">{mark}</span>" in page, f"no use case is marked {mark}"


def test_the_example_call_is_text_a_screen_reader_can_read(settings: Any) -> None:
    settings.CONTACT_EMAIL = ""
    page = landing()
    assert 'id="turn-script"' in page
    assert "Caller: " in page and "Agent: " in page
    assert "Example call · illustrative" in page


def test_the_example_calls_planned_hand_off_is_marked_planned_before_its_words(
    settings: Any,
) -> None:
    """The Hand-off is Planned, so its step shows before the Agent's words and those words are marked planned (never warm)."""
    settings.CONTACT_EMAIL = ""
    page = landing()
    script = page.split('id="turn-script"')[1].split("</ol>")[0]
    step = next(li for li in script.split("<li ")[1:] if 'data-name="Human"' in li)
    line = next(li for li in script.split("<li ")[1:] if "Putting you through" in li)
    assert "data-planned" in step and "data-planned" in line

    def at(li: str) -> float:
        return float(li.split('data-t="')[1].split('"')[0])

    assert at(step) < at(line)


def test_the_portal_showcase_is_a_read_out_and_the_portals_own_module_row_labelled_as_an_example(
    settings: Any,
) -> None:
    settings.CONTACT_EMAIL = ""
    page = landing()
    assert "Example only, not real data" in page
    # The agent as a read-out, not a form: nothing a visitor could fill in or send.
    assert "Example Salon" in page and ">Instructions</p>" in page
    assert ">sv</span>" in page and ">en</span>" in page
    assert "<form" not in page.split('id="portal"')[1].split("</section>")[0]
    # The Portal's own Module row, without its Remove button.
    assert "https://bookings.example.com/mcp" in page
    assert "What it offers" in page and "move_booking" in page
    assert "Remove" not in page


def test_request_access_is_hidden_while_contact_email_is_empty(settings: Any) -> None:
    settings.CONTACT_EMAIL = ""
    page = landing()
    assert "Request access" not in page
    assert "mailto:" not in page


def test_request_access_mails_contact_email_when_it_is_set(settings: Any) -> None:
    settings.CONTACT_EMAIL = "hello@example.com"
    page = landing()
    assert "Request access" in page
    assert 'href="mailto:hello@example.com?subject=Access%20to%20Voice"' in page
    # The address is also written out (in the footer), for a browser that opens no mail app.
    assert ">hello@example.com</a>" in page


def test_the_privacy_notice_is_open_and_linked_from_the_landing_page() -> None:
    """VOI-245: a visitor reads the demo call's notice before calling; it names the controller, a contact and the supervisory authority."""
    response = Client().get(reverse("privacy"))
    assert response.status_code == 200
    page = response.content.decode()
    assert "Privacy notice for the Voice demo call" in page
    assert "Irma AI AB" in page and "559534-1586" in page
    assert 'href="mailto:privacy@getirma.ai"' in page
    assert "Swedish Authority for Privacy Protection (IMY)" in page
    assert f'href="{reverse("privacy")}"' in landing()


def test_without_a_demo_business_the_page_carries_no_call_button(settings: Any) -> None:
    settings.DEMO_BUSINESS_ID = None
    page = landing()
    assert "call-button" not in page and "<script async" not in page


@pytest.mark.db
@pytest.mark.django_db
def test_the_demo_business_call_button_is_the_pasted_tag_and_the_panel_may_reach_the_core(
    settings: Any,
) -> None:
    """With DEMO_BUSINESS_ID set (VOI-244) the page carries that Business's own tag, once it has saved its website like any Business, and a frame-src that lets the panel follow the call link to the core."""
    settings.CORE_URL, settings.PORTAL_URL = (
        "https://voice.example.se/",
        "https://portal.example.se",
    )
    demo, _ = business_with_login("demo@example.com", "Voice itself")
    settings.DEMO_BUSINESS_ID = demo.pk
    assert (
        "call-button" not in landing()
    )  # no website saved yet: the link would refuse, so no button

    demo.website_domain = "portal.example.se"
    demo.save()
    response = Client().get(reverse("home"))
    page = response.content.decode()
    slug = str(demo.call_slug)  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]  (django-stubs types fields for mypy only)
    assert (
        f'<script async src="https://portal.example.se/static/portal/call-button.v2.js?business={slug}"'
        in page
    )
    assert 'integrity="sha384-' in page and page.count("<script async") == 1
    assert ' data-lang="en"' in page  # the English site's label (VOI-244)
    policy = response["Content-Security-Policy"]
    # The tag names PORTAL_URL, not the host this page was served from, so the policy names it too.
    assert "script-src 'self' https://portal.example.se" in policy
    assert (
        "frame-src 'self' https://portal.example.se https://voice.example.se" in policy
    )
    assert "frame-ancestors 'none'" in policy

    settings.DEMO_BUSINESS_ID = demo.pk + 1000  # names no Business: nothing
    response = Client().get(reverse("home"))
    assert "call-button" not in response.content.decode()
    assert "frame-src" not in response["Content-Security-Policy"]


@pytest.mark.db
@pytest.mark.django_db
def test_a_logged_in_business_sees_its_dashboard_link_instead_of_log_in() -> None:
    _, client = business_with_login("user-a@example.com", "Owner A's Salon")
    page = client.get(reverse("home")).content.decode()
    assert f'href="{reverse("dashboard")}"' in page
    assert f'href="{reverse("login")}"' not in page
