"""The settings schema and a check of a served value against it, shared by the Portal's tests."""

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

SCHEMA: dict[str, Any] = json.loads(
    (Path(__file__).parents[2] / "contract/business-settings.schema.json").read_text()
)


def schema_errors(served: Any) -> list[str]:
    validator: Any = Draft202012Validator(SCHEMA)
    return [e.message for e in validator.iter_errors(served)]
