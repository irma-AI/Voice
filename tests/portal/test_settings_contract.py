"""The settings shape lives once, in contract/business-settings.schema.json. These tests fail when the Portal drifts from it and name the side to edit."""

from typing import Any

import pytest
from jsonschema import Draft202012Validator

from portal.accounts import modules as module_rules
from portal.accounts import theme
from portal.accounts.models import (
    LANGUAGES,
    PRIVACY_URL_MAX,
    PRIVACY_URL_PATTERN,
    Account,
    Business,
    Module,
)
from portal.accounts.settings_form import SettingsForm
from tests.portal.contract import SCHEMA, schema_errors

PROPERTIES: dict[str, Any] = SCHEMA["properties"]


def test_the_schema_itself_is_valid() -> None:
    Draft202012Validator.check_schema(SCHEMA)


@pytest.mark.db
@pytest.mark.django_db
def test_what_the_portal_serves_matches_the_schema() -> None:
    business = Business.objects.create(
        account=Account.objects.create_user("user-a@example.com", "x" * 20),
        name="Owner A's Salon",
        instructions="Öppet mån-fre 8-17.",
        languages=["sv", "en"],
    )
    Module.objects.create(business=business, name="bookings", url="https://8.8.8.8/mcp")
    served = business.as_settings()
    errors = schema_errors(served)
    assert not errors, f"edit Business.as_settings or the schema: {errors}"
    assert served["modules"] == [{"name": "bookings", "url": "https://8.8.8.8/mcp"}]


# The Business's Modules have their own page (VOI-28), so they are not among the settings form's fields.
MODULES_PAGE = {"modules"}


# The Business's website domain is Portal-only (VOI-70): the core is never told it.
PORTAL_ONLY = {"website_domain"}

# The form's Theme fields, which the contract carries together as `theme` (VOI-83).
THEME_FIELDS = {"logo", "remove_logo", "use_accent", "accent"}


def test_the_editable_fields_are_exactly_the_schema_properties() -> None:
    fields = set(SettingsForm().fields) - PORTAL_ONLY
    assert THEME_FIELDS <= fields, (
        "SettingsForm lost a Theme field: edit THEME_FIELDS or the form"
    )
    assert fields - THEME_FIELDS | {"theme"} == set(PROPERTIES) - MODULES_PAGE, (
        "SettingsForm.Meta.fields and the schema's properties must list the same settings: edit whichever is wrong"
    )


@pytest.mark.db
@pytest.mark.django_db
def test_what_the_portal_serves_for_a_theme_matches_the_schema() -> None:
    business = Business.objects.create(
        account=Account.objects.create_user("user-a@example.com", "x" * 20),
        name="Owner A's Salon",
        accent="#1c7ed6",
    )
    business.set_logo(b"\x89PNG\r\n\x1a\n" + b"\x00" * 40)
    business.save()
    served = business.as_settings()
    errors = schema_errors(served)
    assert not errors, f"edit Business.theme or the schema: {errors}"
    assert set(served["theme"]) == set(PROPERTIES["theme"]["properties"])  # pyright: ignore[reportArgumentType]


def test_the_accent_is_the_same_colour_rule_in_the_database_and_the_schema() -> None:
    colours = PROPERTIES["theme"]["properties"]
    assert (
        colours["accent"]["pattern"]
        == colours["accent_text"]["pattern"]
        == theme.ACCENT_PATTERN
    ), (
        "set the schema's theme accent patterns and ACCENT_PATTERN in portal/accounts/theme.py to one rule"
    )
    assert Business._meta.get_field("accent").max_length == len("#000000")  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]


def test_the_privacy_notice_address_is_the_same_rule_in_the_database_and_the_schema() -> (
    None
):
    assert PROPERTIES["privacy_url"]["pattern"] == PRIVACY_URL_PATTERN, (
        "set the schema's privacy_url pattern and PRIVACY_URL_PATTERN in portal/accounts/models.py to one rule"
    )
    assert PROPERTIES["privacy_url"]["maxLength"] == PRIVACY_URL_MAX, (
        "set the schema's privacy_url maxLength and PRIVACY_URL_MAX in portal/accounts/models.py to one number"
    )


def test_what_the_portal_serves_for_modules_matches_the_schema() -> None:
    remote, local = (
        PROPERTIES["modules"]["items"]["oneOf"][i]["properties"] for i in (0, 1)
    )
    assert PROPERTIES["modules"]["maxItems"] == module_rules.MODULES_MAX
    assert (
        remote["name"]["maxLength"],
        remote["url"]["maxLength"],
        local["command"]["maxLength"],
        local["args"]["maxItems"],
        local["args"]["items"]["maxLength"],
    ) == (
        module_rules.NAME_MAX,
        module_rules.URL_MAX,
        module_rules.COMMAND_MAX,
        module_rules.ARGS_MAX,
        module_rules.ARG_MAX,
    ), (
        "set contract/business-settings.schema.json and portal/accounts/modules.py to the same numbers"
    )
    for name, longest in (
        ("name", module_rules.NAME_MAX),
        ("url", module_rules.URL_MAX),
        ("command", module_rules.COMMAND_MAX),
    ):
        assert Module._meta.get_field(name).max_length == longest, (  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
            f"set Module.{name} max_length and portal/accounts/modules.py to one number"
        )


def test_each_text_setting_is_as_long_in_the_database_as_in_the_schema() -> None:
    for name, spec in PROPERTIES.items():
        if spec["type"] == "string":
            assert Business._meta.get_field(name).max_length == spec["maxLength"], (  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
                f"set Business.{name} max_length and the schema's maxLength to one number"
            )


def test_the_languages_are_the_same_set_in_the_model_and_the_schema() -> None:
    assert set(LANGUAGES) == set(PROPERTIES["languages"]["items"]["enum"]), (
        "LANGUAGES in models.py and the schema's languages enum must list the same codes"
    )


def test_the_ai_notice_has_no_field_in_the_portal_or_the_contract() -> None:
    names = [
        *PROPERTIES,
        *SettingsForm().fields,
        *(f.name for f in Business._meta.get_fields()),
    ]
    assert not [n for n in names if "notice" in n or "disclosure" in n], (
        "the AI notice is Petter's call and has no setting"
    )
