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


@pytest.mark.db
@pytest.mark.django_db
def test_a_logged_in_business_sees_its_dashboard_link_instead_of_log_in() -> None:
    _, client = business_with_login("anna.testsson@example.com", "Anna's Salon")
    page = client.get(reverse("home")).content.decode()
    assert f'href="{reverse("dashboard")}"' in page
    assert f'href="{reverse("login")}"' not in page
