"""The login and password reset pages still show what they showed before the restyle (make test-db). No mocks of our own code."""

import pytest
from django.test import Client

pytestmark = [pytest.mark.db, pytest.mark.django_db]


@pytest.mark.parametrize(
    ("path", "texts"),
    [
        (
            "/login/",
            ["Log in", "Forgot your password?", 'name="username"', 'name="password"'],
        ),
        (
            "/password-reset/",
            ["Forgot your password?", "Send the link", 'name="email"'],
        ),
        ("/password-reset/sent/", ["Check your email", "is on its way"]),
        ("/password-reset/done/", ["Password saved", 'href="/login/"']),
        (
            "/password-reset/bad/link/",
            ["This link no longer works", "Ask for a new one"],
        ),
    ],
)
def test_each_login_page_shows_its_words(path: str, texts: list[str]) -> None:
    response = Client().get(path, follow=True)
    assert response.status_code == 200
    page = response.content.decode()
    for text in texts:
        assert text in page, (path, text)
