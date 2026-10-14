"""The settings shape lives once, in contract/business-settings.schema.json. These tests fail when the Portal drifts from it and name the side to edit."""

from typing import Any

from jsonschema import Draft202012Validator

from portal.accounts.models import LANGUAGES, Business
from portal.accounts.views import SettingsForm
from tests.portal.contract import SCHEMA, schema_errors

PROPERTIES: dict[str, Any] = SCHEMA["properties"]


def test_the_schema_itself_is_valid() -> None:
    Draft202012Validator.check_schema(SCHEMA)


def test_what_the_portal_serves_matches_the_schema() -> None:
    served = Business(
        name="Anna's Salon", facts="Öppet mån-fre 8-17.", languages=["sv", "en"]
    ).as_settings()
    errors = schema_errors(served)
    assert not errors, f"edit Business.as_settings or the schema: {errors}"


# The core can use Modules (VOI-27) before the Portal can store them: VOI-28 adds the Modules page and empties this set.
NOT_YET_IN_THE_PORTAL = {"modules"}


def test_the_editable_fields_are_exactly_the_schema_properties() -> None:
    assert set(SettingsForm().fields) == set(PROPERTIES) - NOT_YET_IN_THE_PORTAL, (
        "SettingsForm.Meta.fields and the schema's properties must list the same settings: edit whichever is wrong"
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
