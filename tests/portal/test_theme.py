# pyright: basic
# (django-stubs types model fields for mypy's plugin; strict pyright cannot read them)
"""A Business's Theme: a logo and one accent colour, saved on the settings page, refused by the database when malformed,
served publicly by a hash of the logo, and told to the core in the settings contract (make test-db for the marked tests)."""

import hashlib
from typing import Any
from urllib.parse import urlsplit

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import Client

from portal.accounts.models import Business
from portal.accounts.theme import (
    AA_CONTRAST,
    DEEP_SEA,
    FOAM,
    LOGO_MAX_BYTES,
    contrast,
    on_accent,
)
from tests.portal.contract import schema_errors
from tests.portal.helpers import business_with_login

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 40
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 40
WEBP = b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"\x00" * 40
SVG = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
SECRET = "a-secret-for-tests"


def save(client: Client, **theme: Any) -> Any:
    return client.post(
        "/settings/", {"name": "Anna's Salon", "languages": ["sv"], **theme}
    )


def upload(data: bytes, name: str = "logo.png") -> SimpleUploadedFile:
    return SimpleUploadedFile(name, data, content_type="image/png")


def told_to_core(business: Business, settings: Any) -> dict[str, Any]:
    settings.CORE_SECRET = SECRET
    return (
        Client()
        .get(
            f"/api/settings/{business.pk}/",
            headers={"Authorization": f"Bearer {SECRET}"},
        )
        .json()
    )


# --- the accent's contrast: a pure function ---


def test_an_accent_that_already_reads_well_is_unchanged() -> None:
    assert on_accent("#1a2a44") == ("#1a2a44", FOAM)
    assert on_accent("#f5d9a8") == ("#f5d9a8", DEEP_SEA)


def test_a_mid_tone_accent_is_adjusted_just_enough_to_reach_aa() -> None:
    fill, text = on_accent("#1c7ed6")  # a mid blue: neither text reaches 4.5 on it
    assert max(contrast("#1c7ed6", FOAM), contrast("#1c7ed6", DEEP_SEA)) < AA_CONTRAST
    assert fill != "#1c7ed6"
    assert contrast(fill, text) >= AA_CONTRAST


def test_every_accent_comes_out_readable() -> None:
    steps = range(0, 256, 15)
    for r in steps:
        for g in steps:
            for b in steps:
                fill, text = on_accent(f"#{r:02x}{g:02x}{b:02x}")
                assert contrast(fill, text) >= AA_CONTRAST, (fill, text)


# --- the database refuses a malformed Theme, whoever writes it ---


@pytest.mark.parametrize(
    ("logo", "key", "rule"),
    [
        (SVG, None, "business_logo_must_be_png_webp_or_jpeg"),
        (b"GIF89a" + b"\x00" * 40, None, "business_logo_must_be_png_webp_or_jpeg"),
        (b"", None, "business_logo_must_be_png_webp_or_jpeg"),
        (b"RIFF\x00\x00\x00\x00WAVE", None, "business_logo_must_be_png_webp_or_jpeg"),
        (PNG + b"\x00" * LOGO_MAX_BYTES, None, "business_logo_must_be_at_most_256_kb"),
        (PNG, "0" * 64, "business_logo_key_must_be_the_sha256_of_the_logo"),
        (PNG, "", "business_logo_key_must_be_the_sha256_of_the_logo"),
        (None, hashlib.sha256(PNG).hexdigest(), "business_logo_key_must_be_the_sha256"),
    ],
)
@pytest.mark.db
@pytest.mark.django_db
def test_the_database_refuses_a_bad_logo(
    logo: bytes | None, key: str | None, rule: str
) -> None:
    business, _ = business_with_login("anna.testsson@example.com", "Anna's Salon")
    if key is None:
        key = hashlib.sha256(logo).hexdigest() if logo is not None else ""
    # The savepoint keeps the test's own transaction usable after Postgres refuses the write.
    with pytest.raises(IntegrityError, match=rule), transaction.atomic():
        Business.objects.filter(pk=business.pk).update(logo=logo, logo_key=key)


@pytest.mark.parametrize(
    "bad", ["#1A2A44", "1a2a44", "#1a2a4", "#1a2a4g", "#1a2a4 ", "red", "#gggggg"]
)
@pytest.mark.db
@pytest.mark.django_db
def test_the_database_refuses_an_accent_that_is_not_a_six_digit_hex_colour(
    bad: str,
) -> None:
    business, _ = business_with_login("anna.testsson@example.com", "Anna's Salon")
    with (
        pytest.raises(
            IntegrityError,
            match="business_accent_must_be_empty_or_a_six_digit_hex_colour",
        ),
        transaction.atomic(),
    ):
        Business.objects.filter(pk=business.pk).update(accent=bad)


@pytest.mark.parametrize(
    "good", [PNG, JPEG, WEBP, PNG + b"\x00" * (LOGO_MAX_BYTES - len(PNG))]
)
@pytest.mark.db
@pytest.mark.django_db
def test_the_database_takes_a_png_webp_or_jpeg_up_to_the_limit(good: bytes) -> None:
    business, _ = business_with_login("anna.testsson@example.com", "Anna's Salon")
    business.set_logo(good)
    business.save()
    assert bytes(Business.objects.get().logo or b"") == good


# --- the settings page ---


@pytest.mark.db
@pytest.mark.django_db
def test_a_business_saves_a_logo_and_an_accent_and_the_core_is_told(
    settings: Any,
) -> None:
    business, client = business_with_login("anna.testsson@example.com", "Anna's Salon")
    response = save(
        client, logo=upload(WEBP, "logo.png"), use_accent="on", accent="#1A2A44"
    )
    assert response["Location"] == "/settings/?saved=1"

    told = told_to_core(business, settings)

    key = hashlib.sha256(WEBP).hexdigest()
    assert told["theme"] == {
        "accent": "#1a2a44",
        "accent_text": FOAM,
        "logo_url": f"{settings.PORTAL_URL.rstrip('/')}/logo/{key}/",
    }
    assert not schema_errors(told)
    assert str(business.pk) not in told["theme"]["logo_url"].rsplit("/logo/", 1)[1]


@pytest.mark.db
@pytest.mark.django_db
def test_the_core_is_told_the_adjusted_accent(settings: Any) -> None:
    business, client = business_with_login("anna.testsson@example.com", "Anna's Salon")
    save(client, use_accent="on", accent="#1c7ed6")
    theme = told_to_core(business, settings)["theme"]
    assert theme["accent"] != "#1c7ed6"
    assert contrast(theme["accent"], theme["accent_text"]) >= AA_CONTRAST
    page = client.get("/settings/").content.decode()
    assert f"Adjusted from #1c7ed6 to {theme['accent']}" in page


@pytest.mark.db
@pytest.mark.django_db
def test_no_theme_is_voices_own_look_and_the_core_is_told_none(settings: Any) -> None:
    business, client = business_with_login("anna.testsson@example.com", "Anna's Salon")
    save(
        client, accent="#1a2a44"
    )  # the box is unticked: the colour input's value is not saved
    assert Business.objects.get().accent == ""
    assert "theme" not in told_to_core(business, settings)


@pytest.mark.parametrize(
    ("data", "name", "says"),
    [
        (SVG, "logo.svg", "not a PNG, WebP or JPEG"),
        (
            SVG,
            "logo.png",
            "not a PNG, WebP or JPEG",
        ),  # the name does not decide the type
        (b"GIF89a" + b"\x00" * 40, "logo.gif", "not a PNG, WebP or JPEG"),
        (PNG + b"\x00" * LOGO_MAX_BYTES, "logo.png", "the largest is 256 KB"),
    ],
)
@pytest.mark.db
@pytest.mark.django_db
def test_a_wrong_logo_gets_a_clear_error_and_changes_nothing(
    data: bytes, name: str, says: str
) -> None:
    _, client = business_with_login("anna.testsson@example.com", "Anna's Salon")
    save(client, logo=upload(PNG))

    response = save(client, logo=upload(data, name))

    assert response.status_code == 200
    assert says in response.content.decode()
    assert bytes(Business.objects.get().logo or b"") == PNG


@pytest.mark.db
@pytest.mark.django_db
def test_a_malformed_accent_gets_a_clear_error() -> None:
    _, client = business_with_login("anna.testsson@example.com", "Anna's Salon")
    response = save(client, use_accent="on", accent="blue")
    assert response.status_code == 200
    assert "That is not a colour" in response.content.decode()
    assert Business.objects.get().accent == ""


@pytest.mark.db
@pytest.mark.django_db
def test_a_business_removes_its_logo_and_its_accent(settings: Any) -> None:
    business, client = business_with_login("anna.testsson@example.com", "Anna's Salon")
    save(client, logo=upload(PNG), use_accent="on", accent="#1a2a44")
    address = told_to_core(business, settings)["theme"]["logo_url"]
    assert 'alt="Your logo"' in client.get("/settings/").content.decode()

    save(client, accent="#1a2a44")  # untick the accent; the logo stays
    assert told_to_core(business, settings)["theme"] == {"logo_url": address}

    save(client, remove_logo="on")
    found = Business.objects.get()
    assert (found.logo, found.logo_key) == (None, "")
    assert "theme" not in told_to_core(business, settings)
    assert Client().get(urlsplit(address).path).status_code == 404


# --- the public logo address ---


@pytest.mark.parametrize(
    ("data", "kind"), [(PNG, "image/png"), (JPEG, "image/jpeg"), (WEBP, "image/webp")]
)
@pytest.mark.db
@pytest.mark.django_db
def test_the_logo_is_served_publicly_with_its_type_and_a_long_cache(
    data: bytes, kind: str
) -> None:
    _, client = business_with_login("anna.testsson@example.com", "Anna's Salon")
    save(client, logo=upload(data, "logo.png"))

    response = Client().get(f"/logo/{hashlib.sha256(data).hexdigest()}/")

    assert response.status_code == 200
    assert response.content == data
    assert response["Content-Type"] == kind
    assert response["Cache-Control"] == "public, max-age=31536000, immutable"
    assert response["X-Content-Type-Options"] == "nosniff"


@pytest.mark.db
@pytest.mark.django_db
def test_a_logo_address_never_takes_a_business_id_or_a_call_link() -> None:
    business, client = business_with_login("anna.testsson@example.com", "Anna's Salon")
    save(client, logo=upload(PNG))
    for guess in (str(business.pk), business.call_slug, "0" * 64):
        assert Client().get(f"/logo/{guess}/").status_code == 404
