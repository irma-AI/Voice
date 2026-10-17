"""Every Portal page is behind the login unless it is listed open here, so a new page is gated even if its author forgets."""

from django.test import Client
from django.urls import NoReverseMatch, URLPattern, URLResolver, get_resolver, reverse

# Open on purpose: the public page, the login, logout (POST only), the password steps a Business reaches before it has a session,
# the settings address the core calls: it has no session and refuses without the shared secret (tests/portal/test_business_settings.py),
# a Business's public call link, which anyone may open on purpose (tests/portal/test_call_link.py), and the address the call button
# on a Business's website asks for a ticket, which answers only a page the Business listed (tests/portal/test_call_button.py).
OPEN = {
    "home",
    "login",
    "logout",
    "password_reset",
    "password_reset_done",
    "password_reset_confirm",
    "password_reset_complete",
    "settings_for_core",
    "call_link",
    "call_from_site",
}


def route_names(patterns: list[URLPattern | URLResolver]) -> list[str]:
    names: list[str] = []
    for p in patterns:
        if isinstance(p, URLResolver):
            names += route_names(p.url_patterns)
        else:
            assert p.name, (
                f"name the route {p.pattern}: the sweep checks routes by name"
            )
            names.append(p.name)
    return names


def test_every_page_outside_the_open_list_sends_a_visitor_to_the_login() -> None:
    gated = [n for n in route_names(get_resolver().url_patterns) if n not in OPEN]
    assert gated, "nothing was checked"
    for name in gated:
        try:
            address = reverse(name)
        except NoReverseMatch:
            address = reverse(name, args=[1])  # a page of one thing, by its number
        response = Client().get(address)
        assert response.status_code == 302 and response["Location"].startswith(
            "/login/"
        ), f"gate {name} with @login_required, or list it in OPEN with a reason"
