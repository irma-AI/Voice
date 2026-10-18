"""A Business's Theme: its logo and one accent colour, shown only to its Callers (GLOSSARY.md).

The rules the database holds (models.py builds its constraints and the logo's generated type from the tables here),
the reading of an upload, and the contrast adjustment that keeps text on the accent readable.
"""

# The largest logo the database stores, in bytes (about 256 KB).
LOGO_MAX_BYTES = 256 * 1024

# What a logo's bytes start with, per type: (offset, bytes). Read from the bytes, never the file name. No SVG: it can carry script.
LOGO_SIGNATURES: dict[str, tuple[tuple[int, bytes], ...]] = {
    "image/png": ((0, b"\x89PNG\r\n\x1a\n"),),
    "image/jpeg": ((0, b"\xff\xd8\xff"),),
    "image/webp": ((0, b"RIFF"), (8, b"WEBP")),
}

# A six-digit hex colour in lower case: the one spelling the database stores.
ACCENT_PATTERN = r"^#[0-9a-f]{6}$"

# The texts an accent may carry: Foam and Deep sea from portal/static/portal/tokens.css (tests/test_design_tokens.py holds them equal).
FOAM = "#ffffff"
DEEP_SEA = "#0b1322"
# WCAG 2.2 AA for normal-size text (success criterion 1.4.3).
AA_CONTRAST = 4.5

LOGO_PROBLEM = "That file is not a PNG, WebP or JPEG image. Save your logo as one of those and upload it again."
ACCENT_PROBLEM = "That is not a colour. Pick one, or type it as # and six hex digits, for example #1a2a44."


def logo_type(data: bytes) -> str | None:
    """The logo's content type from its first bytes, or None for anything else."""
    for kind, parts in LOGO_SIGNATURES.items():
        if all(data[at : at + len(magic)] == magic for at, magic in parts):
            return kind
    return None


def size_problem(size: int) -> str:
    return f"That logo is {-(-size // 1024)} KB; the largest is {LOGO_MAX_BYTES // 1024} KB. Make it smaller and upload it again."


def parse_accent(text: str) -> str:
    """What a Business typed or picked (`#1A2A44`, `1a2a44`) as the colour to store. Raises ValueError with the sentence to show."""
    text = text.strip().lower()
    if not text.startswith("#"):
        text = "#" + text
    if len(text) != 7 or any(c not in "0123456789abcdef" for c in text[1:]):
        raise ValueError(ACCENT_PROBLEM)
    return text


def _rgb(colour: str) -> tuple[int, int, int]:
    return int(colour[1:3], 16), int(colour[3:5], 16), int(colour[5:7], 16)


def _hex(rgb: tuple[float, float, float]) -> str:
    return "#" + "".join(f"{round(c):02x}" for c in rgb)


def luminance(colour: str) -> float:
    """Relative luminance (WCAG 2.2)."""

    def linear(c: int) -> float:
        s = c / 255
        return s / 12.92 if s <= 0.04045 else ((s + 0.055) / 1.055) ** 2.4

    r, g, b = (linear(c) for c in _rgb(colour))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    """The contrast ratio of two colours (WCAG 2.2), from 1 to 21."""
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def on_accent(accent: str) -> tuple[str, str]:
    """The accent as Callers see it and the text it carries: Foam or Deep sea, whichever reads better, with the accent
    darkened (under Foam) or lightened (under Deep sea) just enough to reach AA. An accent that already passes is unchanged."""
    text = FOAM if contrast(accent, FOAM) >= contrast(accent, DEEP_SEA) else DEEP_SEA
    toward = 0.0 if text == FOAM else 255.0
    r, g, b = _rgb(accent)
    # At step 100 the fill is black or white, which passes against either text.
    for step in range(101):
        t = step / 100
        fill = _hex((r + (toward - r) * t, g + (toward - g) * t, b + (toward - b) * t))
        if contrast(fill, text) >= AA_CONTRAST:
            return fill, text
    raise AssertionError("unreachable: black and white pass against both texts")
