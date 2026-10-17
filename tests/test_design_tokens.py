"""The design tokens are one fact in two places: the Portal's source and the core's call page, which may not import the Portal (ADR 0002)."""

import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
SOURCE = ROOT / "portal/static/portal/tokens.css"
CORE_COPY = ROOT / "voice/page.html"
DECLARATION = re.compile(r"(--[\w-]+)\s*:\s*([^;]+);")


def declarations(text: str, block_start: str) -> dict[str, str]:
    start = text.index(block_start)
    body = text[start : text.index("}", start)]
    return {name: value.strip() for name, value in DECLARATION.findall(body)}


def test_the_call_page_holds_the_same_tokens_as_the_portal_source() -> None:
    source = declarations(SOURCE.read_text("utf-8"), "@theme static {")
    core = declarations(CORE_COPY.read_text("utf-8"), ":root {")
    assert len(source) >= 5, "nothing was read from the token source"
    assert core == source, (
        "the tokens differ: edit portal/static/portal/tokens.css (the source), "
        "then copy its declarations into the first :root block of voice/page.html"
    )
