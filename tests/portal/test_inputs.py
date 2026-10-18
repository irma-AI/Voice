# pyright: basic
# (django-stubs types model fields for mypy's plugin; strict pyright cannot read them)
"""The Portal's input fields under real use: odd and long input, a refused form that keeps what was typed and says what to fix,
an expired form or session that says what happened (make test-db). No mocks of our own code."""

import re
from typing import Any

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from portal.accounts.models import Business, Module
from portal.accounts.views import INSTRUCTIONS_MAX
from tests.portal.helpers import PASSWORD, business_with_login

pytestmark = [pytest.mark.db, pytest.mark.django_db]

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 40
PUBLIC = "https://8.8.8.8/mcp"


@pytest.fixture(autouse=True)
def hosted(settings: Any) -> None:
    settings.CORE_SECRET = "a-secret-for-tests"
    settings.CORE_URL = "https://voice.example.se/"
    settings.ALLOW_LOCAL_MODULES = False


def settings_post(client: Client, **fields: Any) -> Any:
    return client.post(
        "/settings/", {"name": "Anna's Salon", "languages": ["sv"], **fields}
    )


# --- log in ---


def test_a_wrong_password_is_said_once_and_the_email_is_kept() -> None:
    business_with_login("anna.testsson@example.com", "Anna's Salon")
    page = (
        Client()
        .post("/login/", {"username": "Anna.Testsson@example.com", "password": "wrong"})
        .content.decode()
    )
    assert page.count("That email and password do not match") == 1
    assert "case-sensitive" not in page  # the email is not
    assert 'value="Anna.Testsson@example.com"' in page
    assert "wrong" not in page  # a password is never sent back


def test_an_ended_session_says_so_and_a_pressed_button_lands_on_its_page() -> None:
    business_with_login("anna.testsson@example.com", "Anna's Salon")
    visitor = Client()

    # The session ended while the Test call button was on screen: the press goes to the login, which says why.
    sent_to = visitor.post("/test-call/")["Location"]
    assert sent_to == "/login/?next=/test-call/"
    assert "You are logged out" in visitor.get(sent_to).content.decode()
    assert "You are logged out" not in Client().get("/login/").content.decode()

    # Logging in goes back to the address, which starts no call on a GET but shows the button again.
    after = visitor.post(
        sent_to, {"username": "anna.testsson@example.com", "password": PASSWORD}
    )
    assert after["Location"] == "/test-call/"
    back = visitor.get("/test-call/")
    assert back["Location"] == "/dashboard/" and "ticket" not in back["Location"]


# --- an expired form (CSRF) ---


@pytest.mark.parametrize("path", ["/login/", "/settings/", "/test-call/"])
def test_a_form_without_a_valid_token_is_refused_with_a_page_that_says_what_to_do(
    path: str,
) -> None:
    business, logged_in = business_with_login("anna.testsson@example.com", "Anna")
    strict = Client(enforce_csrf_checks=True)
    strict.cookies = logged_in.cookies

    response = strict.post(
        path, {"name": "Changed", "languages": ["sv"], "username": "x", "password": "y"}
    )

    assert response.status_code == 403
    page = response.content.decode()
    assert "That form was not sent" in page
    assert "Nothing was changed" in page
    assert f'href="{path}"' in page
    assert "CSRF" not in page  # Django's own page names the mechanism, not the remedy
    assert Business.objects.get(pk=business.pk).name == "Anna"


def test_a_refused_log_out_links_to_a_page_that_opens() -> None:
    _, logged_in = business_with_login("anna.testsson@example.com", "Anna")
    strict = Client(enforce_csrf_checks=True)
    strict.cookies = logged_in.cookies
    page = strict.post("/logout/").content.decode()
    assert 'href="/"' in page and 'href="/logout/"' not in page


# --- settings ---


def test_a_refused_save_lists_what_to_fix_at_the_top_and_keeps_what_was_typed() -> None:
    _, client = business_with_login("anna.testsson@example.com", "Anna's Salon")
    page = settings_post(
        client,
        name="   ",
        instructions="Öppet mån–fre 🙂 ﷽",
        languages=[],
        website_domain="localhost",
    ).content.decode()

    summary = page.split('class="error-summary', 1)[1].split("</div>", 1)[0]
    assert 'role="alert"' in summary and "Nothing was saved" in summary
    assert 'href="#id_name"' in summary and "Give your business a name." in summary
    assert (
        'href="#id_languages"' in summary and "Pick at least one language." in summary
    )
    assert 'href="#id_website_domain"' in summary and "not a website domain" in summary
    assert "Öppet mån–fre 🙂 ﷽" in page  # kept, unicode and all
    assert 'value="localhost"' in page
    assert "Saved." not in page
    assert Business.objects.get().name == "Anna's Salon"


def test_facts_count_a_line_break_as_one_character_as_the_browser_does() -> None:
    business, client = business_with_login("anna.testsson@example.com", "Anna")
    limit = INSTRUCTIONS_MAX  # the model's own limit
    assert limit == 5000
    # 5,000 characters in the browser's count, sent with the two-character line breaks every browser sends
    typed = "\r\n".join(["x" * 99] * 50) + "x"
    assert len(typed.replace("\r\n", "\n")) == limit

    assert settings_post(client, instructions=typed)["Location"] == "/settings/?saved=1"
    business.refresh_from_db()
    assert business.instructions == typed.replace("\r\n", "\n")

    too_long = settings_post(client, instructions="x" * (limit + 1)).content.decode()
    assert "at most 5000 characters" in too_long


def test_the_settings_fields_carry_their_limits_and_the_right_keyboards() -> None:
    _, client = business_with_login("anna.testsson@example.com", "Anna")
    page = client.get("/settings/").content.decode()
    instructions = re.search(r"<textarea[^>]*>", page)
    assert instructions and 'maxlength="5000"' in instructions.group(0)
    assert "Up to 5,000 characters." in page
    assert 'data-count="id_instructions"' in page
    name = re.search(r'<input[^>]*name="name"[^>]*>', page)
    assert name and 'maxlength="200"' in name.group(0)
    assert 'autocomplete="organization"' in name.group(0)
    website = re.search(r'<input[^>]*name="website_domain"[^>]*>', page)
    assert website and 'inputmode="url"' in website.group(0)
    assert 'autocapitalize="none"' in website.group(0)


def test_an_international_domain_is_shown_as_its_owner_writes_it() -> None:
    business, client = business_with_login("anna.testsson@example.com", "Anna")
    settings_post(client, website_domain="https://www.Räksmörgås.SE/boka")
    business.refresh_from_db()
    assert business.website_domain == "xn--rksmrgs-5wao1o.se"  # what browsers send
    assert 'value="räksmörgås.se"' in client.get("/settings/").content.decode()
    assert "räksmörgås.se" in client.get("/dashboard/").content.decode()
    # Saving the page again keeps the same domain.
    settings_post(client, website_domain="räksmörgås.se")
    business.refresh_from_db()
    assert business.website_domain == "xn--rksmrgs-5wao1o.se"


def test_a_logo_picked_in_a_refused_save_is_asked_for_again() -> None:
    _, client = business_with_login("anna.testsson@example.com", "Anna")
    page = settings_post(
        client,
        name="",
        logo=SimpleUploadedFile("logo.png", PNG, content_type="image/png"),
    ).content.decode()
    assert "Choose your logo again" in page
    assert Business.objects.get().logo is None


def test_remove_my_logo_stays_ticked_after_a_refused_save() -> None:
    business, client = business_with_login("anna.testsson@example.com", "Anna")
    business.set_logo(PNG)
    business.save()
    page = settings_post(client, name="", remove_logo="on").content.decode()
    box = re.search(r'<input[^>]*name="remove_logo"[^>]*>', page)
    assert box and "checked" in box.group(0)
    assert Business.objects.get().logo is not None


# --- Modules ---


def test_a_refused_module_says_what_is_missing_once_and_keeps_what_was_typed() -> None:
    _, client = business_with_login("anna.testsson@example.com", "Anna")
    page = client.post("/modules/", {"name": "  ", "address": ""}).content.decode()
    assert "Give the Module a name." in page
    assert "Give the Module&#x27;s address." in page

    page = client.post(
        "/modules/",
        {"name": "Bokning 📅", "address": "https://user:pw@example.com/mcp"},
    ).content.decode()
    assert page.count("That is not a plain address") == 1
    assert 'value="Bokning 📅"' in page
    assert Module.objects.count() == 0


def test_a_long_module_name_is_kept_whole_and_wraps() -> None:
    business, client = business_with_login("anna.testsson@example.com", "Anna")
    name = "Bokningssystemets-integrationsmodul-" * 2 + "x" * 28
    assert len(name) == 100
    assert (
        client.post("/modules/", {"name": name, "address": PUBLIC}).status_code == 302
    )
    page = client.get("/modules/").content.decode()
    assert f'<p class="text-lg font-medium break-words">{name}</p>' in page
    over = client.post("/modules/", {"name": name + "y", "address": PUBLIC})
    assert "at most 100 characters" in over.content.decode()
    assert Module.objects.filter(business=business).count() == 1


def test_every_page_loads_the_script_that_sends_a_form_once() -> None:
    _, client = business_with_login("anna.testsson@example.com", "Anna")
    for path in ("/settings/", "/modules/", "/tokens/", "/dashboard/"):
        assert "portal/portal.js" in client.get(path).content.decode(), path
    assert "portal/portal.js" in Client().get("/login/").content.decode()
