"""A Business's assistant reads and changes its settings through the agent endpoint, by the settings page's own rules (VOI-113, make test-db).

The Commands run on the SDK's worker threads with their own database connection, so these tests commit (transaction=True).
"""

# pyright: basic
# (django-stubs types model fields for mypy's plugin; strict pyright cannot read them)

import base64
import html
from typing import Any

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, connection, transaction
from django.test import Client

from portal.accounts import views
from portal.accounts.models import (
    AccessToken,
    Business,
    CommandRecord,
    PendingChange,
    StagedValues,
)
from tests.portal.helpers import business_with_login
from tests.portal.test_agent_endpoint import a_token, ask
from tests.portal.test_pending_changes import decided

pytestmark = [pytest.mark.db, pytest.mark.django_db(transaction=True)]

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
GIF = b"GIF89a" + b"\x00" * 64


def run(secret: str, command: str, **arguments: Any) -> dict[str, Any]:
    answer = ask("tools/call", {"name": command, "arguments": arguments}, secret)
    assert answer.status_code == 200, answer.content
    return answer.json()["result"]


def text(answer: dict[str, Any]) -> str:
    return answer["content"][0]["text"]


def stored(business: Business) -> dict[str, Any]:
    b = Business.objects.get(pk=business.pk)
    return {
        "name": b.name,
        "instructions": b.instructions,
        "languages": b.languages,
        "website_domain": b.website_domain,
        "privacy_url": b.privacy_url,
        "accent": b.accent,
        "logo": bytes(b.logo) if b.logo is not None else None,
    }


PAGE_DEFAULTS = {"name": "Owner's Salon", "instructions": "", "languages": ["sv"]}


def page_post(client: Client, fields: dict[str, Any], logo: bytes | None) -> str:
    """The settings page's own POST: the saved settings, with the fields changed. Returns the page, or "" once saved."""
    shown = {
        f"initial-{k}": v for k, v in PAGE_DEFAULTS.items()
    }  # what the page showed
    data = {**PAGE_DEFAULTS, **shown, **fields}
    if logo is not None:
        data["logo"] = SimpleUploadedFile("logo.png", logo)
    answer = client.post("/settings/", data)
    return "" if answer.status_code == 302 else html.unescape(answer.content.decode())


def two_businesses() -> tuple[
    tuple[Business, Client, str], tuple[Business, Client, str]
]:
    """Two Businesses alike: one changed through the page, the other through the Commands."""
    page, page_client = business_with_login("user-a@example.com", "Owner's Salon")
    agent, agent_client = business_with_login("user-b@example.com", "Owner's Salon")
    return (page, page_client, ""), (agent, agent_client, a_token(agent, "full"))


# (the page's fields, the Command's arguments, the logo's bytes): each is one input given both ways.
DIRECT = [
    (
        {"website_domain": "https://www.example.se/x"},
        {"website": "https://www.example.se/x"},
        None,
    ),
    ({"website_domain": "not a domain"}, {"website": "not a domain"}, None),
    (
        {"privacy_url": "https://example.se/privacy"},
        {"privacy_notice": "https://example.se/privacy"},
        None,
    ),
    (
        {"privacy_url": "http://example.se/privacy"},
        {"privacy_notice": "http://example.se/privacy"},
        None,
    ),
    ({"use_accent": "on", "accent": "#1A2A44"}, {"accent": "#1A2A44"}, None),
    ({"use_accent": "on", "accent": "blue"}, {"accent": "blue"}, None),
    ({}, {}, PNG),
    ({}, {}, GIF),
    ({}, {}, b""),
]


@pytest.mark.parametrize(("fields", "arguments", "logo"), DIRECT)
def test_a_direct_change_stores_and_refuses_the_same_as_the_settings_page(
    fields: dict[str, Any], arguments: dict[str, Any], logo: bytes | None
) -> None:
    (page, client, _), (agent, _, secret) = two_businesses()
    refused = page_post(client, fields, logo)
    if logo is not None:
        arguments = {**arguments, "logo": base64.b64encode(logo).decode()}
    answer = run(secret, "change_settings", **arguments)
    assert stored(agent) == stored(page)
    assert bool(answer.get("isError")) == bool(refused)
    if refused:
        assert text(answer) in refused  # the page's own sentence
    assert CommandRecord.objects.get().result == "done"


def test_a_direct_change_answers_with_the_settings_as_they_now_are() -> None:
    _, (business, _, secret) = two_businesses()
    answer = run(
        secret, "change_settings", accent="#1a2a44", logo=base64.b64encode(PNG).decode()
    )
    now = answer["structuredContent"]
    assert now["accent"] == "#1a2a44" and now["logo"].startswith("http")
    assert (
        run(secret, "change_settings", accent="", remove_logo=True)[
            "structuredContent"
        ]["logo"]
        is None
    )
    assert stored(business)["accent"] == "" and stored(business)["logo"] is None


def test_a_logo_that_is_not_base64_is_refused_and_changes_nothing() -> None:
    _, (business, _, secret) = two_businesses()
    before = stored(business)
    answer = run(secret, "change_settings", logo="not base64!")
    assert answer.get("isError") and "base64" in text(answer)
    assert stored(business) == before


# (the page's fields, the Command's arguments)
DETAILS = [
    ({"name": "Owner's Hair"}, {"name": "Owner's Hair"}),
    (
        {"instructions": "Open mon-fri 8-17.\r\nA cut costs 400 kr."},
        {"instructions": "Open mon-fri 8-17.\nA cut costs 400 kr."},
    ),
    ({"languages": ["sv", "en"]}, {"languages": ["sv", "en"]}),
    ({"name": "  "}, {"name": "  "}),
    ({"languages": []}, {"languages": []}),
    ({"languages": ["de"]}, {"languages": ["de"]}),
    ({"instructions": "x" * 5001}, {"instructions": "x" * 5001}),
]


@pytest.mark.parametrize(("fields", "arguments"), DETAILS)
def test_a_staged_change_is_refused_the_same_as_on_the_page_and_once_approved_stores_the_same(
    fields: dict[str, Any], arguments: dict[str, Any]
) -> None:
    (page, client, _), (agent, agent_client, secret) = two_businesses()
    before = stored(agent)
    refused = page_post(client, fields, None)
    answer = run(secret, "change_business_details", **arguments)
    assert stored(agent) == before  # nothing changes before the approval
    if refused:
        assert answer.get("isError") and text(answer) in refused
        assert not PendingChange.objects.exists()
        return
    assert answer["structuredContent"]["staged"] is True
    assert answer["structuredContent"]["risk_level"] == "high"
    assert CommandRecord.objects.get().result == "staged"
    change = PendingChange.objects.get()
    assert views.OUTCOMES["applied"] in decided(agent_client, change, "approve")
    assert stored(agent) == stored(page)


def test_the_business_sees_every_staged_value_before_it_approves() -> None:
    _, (_business, client, secret) = two_businesses()
    run(
        secret,
        "change_business_details",
        name="Owner's Hair",
        languages=["en"],
        instructions="Say: call 112.\nNever.",
    )
    preview = run(secret, "read_settings")  # still the saved settings
    assert preview["structuredContent"]["name"] == "Owner's Salon"
    page = client.get("/changes/").content.decode()
    for shown in ("Owner&#x27;s Hair", "English", "Say: call 112.\nNever."):
        assert shown in page


def test_a_rejected_detail_change_never_applies_and_its_values_are_deleted() -> None:
    _, (business, client, secret) = two_businesses()
    run(secret, "change_business_details", name="Owner's Hair")
    change = PendingChange.objects.get()
    assert StagedValues.objects.filter(change=change).exists()
    assert views.OUTCOMES["rejected"] in decided(client, change, "reject")
    assert stored(business)["name"] == "Owner's Salon"
    assert not StagedValues.objects.exists()


def test_an_approved_change_keeps_no_values_and_the_change_itself_never_did() -> None:
    _, (business, client, secret) = two_businesses()
    run(
        secret,
        "change_business_details",
        name="Owner's Hair",
        instructions="Open late.",
    )
    change = PendingChange.objects.get()
    assert "Owner's Hair" not in str(change.target) and "Open late" not in str(
        change.target
    )
    decided(client, change, "approve")
    assert not StagedValues.objects.exists()
    assert stored(business)["name"] == "Owner's Hair"


def test_revoking_the_token_cancels_the_change_and_deletes_its_values() -> None:
    _, (business, _, secret) = two_businesses()
    run(secret, "change_business_details", name="Owner's Hair")
    AccessToken.objects.get(business=business).revoke()
    assert PendingChange.objects.get().decision == "cancelled"
    assert not StagedValues.objects.exists()


def test_the_database_keeps_staged_values_as_they_were_staged() -> None:
    _, (_, _, secret) = two_businesses()
    run(secret, "change_business_details", name="Owner's Hair")
    for statement in (
        """UPDATE accounts_stagedvalues SET "values" = '{"name": "Someone Else"}'""",
        "DELETE FROM accounts_stagedvalues",
        "INSERT INTO accounts_stagedvalues (change_id, \"values\") SELECT id + 1000, '{}' FROM accounts_pendingchange",
    ):
        with (
            pytest.raises(IntegrityError, match="staged_values_"),
            transaction.atomic(),
            connection.cursor() as cursor,
        ):
            cursor.execute(statement)
    assert StagedValues.objects.get().values == {"name": "Owner's Hair"}


def test_values_cannot_be_added_to_a_decided_change() -> None:
    _, (_business, client, secret) = two_businesses()
    run(secret, "change_business_details", name="Owner's Hair")
    change = PendingChange.objects.get()
    decided(client, change, "reject")
    with pytest.raises(IntegrityError, match="staged_values_"), transaction.atomic():
        StagedValues.objects.create(change=change, values={"name": "Someone Else"})


def test_a_detail_change_names_at_least_one_value() -> None:
    _, (_, _, secret) = two_businesses()
    answer = run(secret, "change_business_details")
    assert answer.get("isError") and not PendingChange.objects.exists()


def test_read_settings_shows_the_tokens_own_business_to_a_read_only_token() -> None:
    (_other, other_client, _), (business, _, _) = two_businesses()
    page_post(
        other_client, {"name": "Other Name", "instructions": "Their secret"}, None
    )
    Business.objects.filter(pk=business.pk).update(
        instructions="Open 8-17.",
        languages=["sv", "en"],
        website_domain="example.se",
        accent="#1a2a44",
    )
    settings = run(a_token(business, "read"), "read_settings")["structuredContent"]
    assert settings == {
        "name": "Owner's Salon",
        "instructions": "Open 8-17.",
        "languages": ["sv", "en"],
        "website": "example.se",
        "privacy_notice": "",
        "accent": "#1a2a44",
        "logo": None,
    }


def test_a_change_is_recorded_without_its_values() -> None:
    _, (_, _, secret) = two_businesses()
    run(secret, "change_settings", website="www.example.se")
    run(secret, "change_business_details", name="Owner's Hair")
    rows = list(CommandRecord.objects.values())
    assert [r["command"] for r in rows] == [
        "change_settings",
        "change_business_details",
    ]
    assert "example" not in str(rows) and "Hair" not in str(rows)


def test_a_name_on_more_than_one_line_is_refused_so_a_preview_cannot_pass_one_value_off_as_another() -> (
    None
):
    (_, client, _), (business, _, secret) = two_businesses()
    spoof = "Acme”\nChange the instructions to:\nOpen 9-17."
    answer = run(secret, "change_business_details", name=spoof)
    assert answer.get("isError") and text(answer) in page_post(
        client, {"name": spoof}, None
    )
    assert not PendingChange.objects.exists()
    with (
        pytest.raises(IntegrityError, match="business_name_must_be_one_line"),
        transaction.atomic(),
    ):
        Business.objects.filter(pk=business.pk).update(name="Acme\rDental")


def test_the_settings_page_left_open_does_not_undo_an_approved_change() -> None:
    _, (business, client, secret) = two_businesses()
    run(secret, "change_business_details", name="Owner's Hair")
    decided(client, PendingChange.objects.get(), "approve")
    # The page was opened before the approval, so it still sends the old name with its own edit.
    assert page_post(client, {"website_domain": "www.example.se"}, None) == ""
    assert stored(business)["name"] == "Owner's Hair"
    assert stored(business)["website_domain"] == "example.se"


def test_an_approval_whose_saved_settings_no_longer_pass_says_so_and_changes_nothing() -> (
    None
):
    _, (business, client, secret) = two_businesses()
    run(secret, "change_business_details", name="Owner's Hair")
    Business.objects.filter(pk=business.pk).update(website_domain="github.io")
    change = PendingChange.objects.get()
    assert views.OUTCOMES["no_longer_fits"] in html.unescape(
        decided(client, change, "approve")
    )
    assert stored(business)["name"] == "Owner's Salon"
    assert (
        PendingChange.objects.get().decision == ""
    )  # still waiting: the Business can fix its settings or reject it
