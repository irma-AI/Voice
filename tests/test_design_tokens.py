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


def test_design_md_names_the_same_colours_as_the_token_source() -> None:
    source = declarations(SOURCE.read_text("utf-8"), "@theme static {")
    colours = {
        name.removeprefix("--color-"): value
        for name, value in source.items()
        if name.startswith("--color-")
    }
    front = (ROOT / "DESIGN.md").read_text("utf-8").split("---")[1]
    design: dict[str, str] = {}
    for line in front[front.index("colors:") :].splitlines()[1:]:
        if not line.startswith("  "):
            break
        name, value = line.strip().split(":", 1)
        design[name] = value.strip().strip('"')
    assert len(colours) >= 5, "nothing was read from the token source"
    assert design == colours, (
        "DESIGN.md's colors differ from the tokens: edit portal/static/portal/tokens.css (the source), "
        "then copy its colours into the colors frontmatter of DESIGN.md"
    )
