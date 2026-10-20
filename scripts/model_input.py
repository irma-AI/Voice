"""Prints what the model is sent for each eval Business, as JSON: the eval receipt hashes this (scripts/eval-receipt.js).

The system instruction and the tool declarations as `voice/agent.py` builds them, the model and the VAD settings.
So an edit to voice/settings.py or voice/modules.py that the model never sees (a theme key, the privacy_url) needs
no paid run, and one that changes what it is sent does. Starts the example Modules locally; calls nothing paid.
"""

import asyncio
import json
from pathlib import Path

from voice.agent import system_instruction
from voice.bargein import VAD
from voice.cost import MODEL
from voice.modules import connect_modules
from voice.settings import load_settings


async def render(business: Path) -> dict[str, object]:
    settings = load_settings({"SETTINGS_FILE": str(business)})
    # A long wait: a slow CI runner must not drop a Module and so change the hash.
    modules = await connect_modules(settings.modules, allow_local=True, timeout=60)
    try:
        if len(modules.clients) != len(settings.modules):
            raise SystemExit(
                f"{business}: a Module did not connect (see the log above), so its tools cannot be hashed"
            )
        return {
            "system_instruction": system_instruction(
                settings, has_actions=bool(modules.actions)
            ),
            "tools": [a.to_default_dict() for a in modules.actions],
        }
    finally:
        await modules.close()


async def main() -> None:
    businesses = sorted(Path("tests/evals").glob("business*.json"))
    if not businesses:
        raise SystemExit("no tests/evals/business*.json: nothing to render")
    out = {
        "model": MODEL,
        "vad": VAD.model_dump(mode="json"),
        "businesses": {b.name: await render(b) for b in businesses},
    }
    print(json.dumps(out, sort_keys=True, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    asyncio.run(main())
