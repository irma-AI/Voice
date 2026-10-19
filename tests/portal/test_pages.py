# pyright: basic
# (django-stubs types model fields for mypy's plugin; strict pyright cannot read them)
"""The login and password reset pages still show what they showed before the restyle (make test-db). No mocks of our own code."""

import pytest
from django.test import Client
from django.urls import NoReverseMatch, get_resolver, reverse

from portal.accounts.models import Business
from tests.portal.helpers import business_with_login
from tests.portal.test_routes import route_names

pytestmark = [pytest.mark.db, pytest.mark.django_db]


@pytest.mark.parametrize(
    ("path", "texts"),
    [
        (
            "/login/",
            [
                "Log in",
                "Forgot your password?",
                'name="username"',
                'name="password"',
                'type="email"',  # a phone shows the email keyboard
            ],
        ),
        (
            "/password-reset/",
            [
                "Forgot your password?",
                "Send the link",
                'name="email"',
                'href="/login/"',
            ],
        ),
        (
            "/password-reset/sent/",
            ["Check your email", "is on its way", 'href="/login/"'],
        ),
        ("/password-reset/done/", ["Password saved", 'href="/login/"']),
        (
            "/password-reset/bad/link/",
            [
                "<title>This link no longer works",  # the tab says what the page says
                "Ask for a new one",
            ],
        ),
    ],
)
def test_each_login_page_shows_its_words(path: str, texts: list[str]) -> None:
    response = Client().get(path, follow=True)
    assert response.status_code == 200
    page = response.content.decode()
    for text in texts:
        assert text in page, (path, text)


PAGES = "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'"


def test_every_page_has_the_csp_the_logo_its_own_and_the_call_link_no_frame_rule() -> (
    None
):
    business, logged_in = business_with_login(
        "anna.testsson@example.com", "Anna's Salon"
    )
    business.set_logo(b"\x89PNG\r\n\x1a\n" + b"\x00" * 40)
    Business.objects.filter(pk=business.pk).update(website_domain="anna.example.se")
    business.save()
    business.refresh_from_db()
    special = {"logo", "call_link"}
    names = [n for n in route_names(get_resolver().url_patterns) if n not in special]
    assert names, "nothing was checked"
    for name in names:
        try:
            address = reverse(name)
        except NoReverseMatch:  # a page of one thing, or a reset link
            try:
                address = reverse(name, args=[1])
            except NoReverseMatch:
                address = reverse(name, args=["MQ", "set-password"])
        for client in (Client(), logged_in):
            response = client.get(address)
            assert (
                response["Content-Security-Policy"]
                == PAGES + "; frame-ancestors 'none'"
            ), (name, response.status_code)

    logo = Client().get(f"/logo/{business.logo_key}/")
    assert logo.status_code == 200
    assert logo["Content-Security-Policy"] == "default-src 'none'"

    for headers in (
        {"Sec-Fetch-Dest": "iframe"},
        {},
    ):  # the redirect, and the refusal page
        call = Client().get(f"/call/{business.call_slug}/", headers=headers)
        assert call["Content-Security-Policy"] == PAGES, call.status_code
