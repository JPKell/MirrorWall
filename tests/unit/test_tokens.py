"""The design tokens: contrast in both themes, and tokens.json agreeing with tokens.css.

The contrast numbers are computed here, not asserted from a spreadsheet. UI standards §7 calls
4.5:1 for body text and 3:1 for a UI boundary non-negotiable, and a palette is exactly the kind of
thing that drifts one hex digit at a time until it no longer meets them.
"""

from __future__ import annotations

import json
import re

import pytest

from mirrorwall import PACKAGE_STATIC_DIR

TOKENS_CSS = PACKAGE_STATIC_DIR / "css" / "tokens.css"
TOKENS_JSON = PACKAGE_STATIC_DIR / "css" / "tokens.json"

# (foreground, background, minimum ratio, what it is)
TEXT_PAIRS = [
    ("--mw-text", "--mw-bg", 4.5, "body text on the page background"),
    ("--mw-text", "--mw-surface", 4.5, "body text on a card"),
    ("--mw-text", "--mw-surface-alt", 4.5, "body text on a table header"),
    ("--mw-text-muted", "--mw-bg", 4.5, "muted text on the page background"),
    ("--mw-text-muted", "--mw-surface", 4.5, "muted text on a card"),
    ("--mw-text-subtle", "--mw-surface", 4.5, "subtle text on a card"),
    ("--mw-accent-text", "--mw-bg", 4.5, "link text on the page background"),
    ("--mw-accent-text", "--mw-surface", 4.5, "link text on a card"),
    ("--mw-success", "--mw-surface", 4.5, "a success word on a card"),
    ("--mw-warning", "--mw-surface", 4.5, "a warning word on a card"),
    ("--mw-danger", "--mw-surface", 4.5, "a danger word on a card"),
    ("--mw-info", "--mw-surface", 4.5, "an info word on a card"),
]

UI_PAIRS = [
    ("--mw-border-strong", "--mw-surface", 3.0, "the boundary of an interactive control"),
    ("--mw-accent", "--mw-surface", 3.0, "the focus ring against a card"),
    ("--mw-accent", "--mw-bg", 3.0, "the focus ring against the page"),
    # The status-dot vocabulary (design brief §3): the dot alone carries the colour, the word
    # beside it stays plain text, so each dot is a UI boundary — 3:1 — not a text obligation.
    ("--mw-status-ok", "--mw-surface", 3.0, "the ok status dot"),
    ("--mw-status-degraded", "--mw-surface", 3.0, "the degraded status dot"),
    ("--mw-status-stopped", "--mw-surface", 3.0, "the stopped status dot"),
    ("--mw-status-unknown", "--mw-surface", 3.0, "the unknown status dot"),
    ("--mw-chart-1", "--mw-surface", 3.0, "the first chart series"),
    ("--mw-chart-2", "--mw-surface", 3.0, "the second chart series"),
    ("--mw-chart-3", "--mw-surface", 3.0, "the third chart series"),
    ("--mw-chart-4", "--mw-surface", 3.0, "the fourth chart series"),
    ("--mw-chart-5", "--mw-surface", 3.0, "the fifth chart series"),
    ("--mw-chart-6", "--mw-surface", 3.0, "the sixth chart series"),
]


def _channel(value: int) -> float:
    srgb = value / 255
    return srgb / 12.92 if srgb <= 0.04045 else ((srgb + 0.055) / 1.055) ** 2.4


def _luminance(hex_colour: str) -> float:
    """Relative luminance per WCAG 2.1's own definition."""
    raw = hex_colour.lstrip("#")
    red, green, blue = (int(raw[index : index + 2], 16) for index in (0, 2, 4))
    return 0.2126 * _channel(red) + 0.7152 * _channel(green) + 0.0722 * _channel(blue)


def contrast(foreground: str, background: str) -> float:
    """The WCAG contrast ratio between two opaque colours."""
    lighter, darker = sorted((_luminance(foreground), _luminance(background)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def _palettes() -> dict[str, dict[str, str]]:
    payload = json.loads(TOKENS_JSON.read_text())
    light = dict(payload["light"])
    dark = {**light, **payload["dark"]}
    return {"light": light, "dark": dark}


PALETTES = _palettes()


def test_the_ratio_function_agrees_with_wcag_worked_examples() -> None:
    """Black on white is 21:1 exactly; a colour against itself is 1:1."""
    assert contrast("#000000", "#ffffff") == pytest.approx(21.0, abs=0.01)
    assert contrast("#2F80ED", "#2F80ED") == pytest.approx(1.0, abs=0.001)


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize(("foreground", "background", "minimum", "what"), TEXT_PAIRS + UI_PAIRS)
def test_every_token_pair_meets_its_contrast_floor(
    theme: str, foreground: str, background: str, minimum: float, what: str
) -> None:
    palette = PALETTES[theme]
    ratio = contrast(palette[foreground], palette[background])
    assert ratio >= minimum, (
        f"{what} in {theme}: {foreground} on {background} is {ratio:.2f}:1, below {minimum}:1"
    )


def test_tokens_json_matches_tokens_css_exactly() -> None:
    """A second copy of the palette is only useful while it cannot disagree with the first."""
    css = TOKENS_CSS.read_text()

    def block(pattern: str) -> dict[str, str]:
        match = re.search(pattern, css, re.S | re.M)
        assert match, pattern
        return {
            name: value.split("/*")[0].strip()
            for name, value in re.findall(r"(--mw-[a-z0-9-]+)\s*:\s*([^;]+);", match.group(1))
        }

    payload = json.loads(TOKENS_JSON.read_text())
    assert payload["light"] == block(r"^:root \{$(.*?)^\}$")
    assert payload["dark"] == block(r'^:root\[data-theme="dark"\] \{$(.*?)^\}$')


def test_the_media_query_and_the_explicit_dark_attribute_define_the_same_palette() -> None:
    """A toggle that lands somewhere the system setting does not is two dark themes, not one."""
    css = TOKENS_CSS.read_text()
    media = re.search(r':root:not\(\[data-theme="light"\]\) \{(.*?)\n  \}', css, re.S)
    explicit = re.search(r'^:root\[data-theme="dark"\] \{$(.*?)^\}$', css, re.S | re.M)
    assert media and explicit

    def parse(body: str) -> dict[str, str]:
        return dict(re.findall(r"(--mw-[a-z0-9-]+)\s*:\s*([^;]+);", body))

    assert parse(media.group(1)) == parse(explicit.group(1))


def test_no_colour_is_defined_only_inside_a_media_query() -> None:
    css = TOKENS_CSS.read_text()
    root = re.search(r"^:root \{$(.*?)^\}$", css, re.S | re.M)
    assert root
    defined_on_root = set(re.findall(r"(--mw-[a-z0-9-]+)\s*:", root.group(1)))
    everywhere = set(re.findall(r"(--mw-[a-z0-9-]+)\s*:", css))
    assert everywhere == defined_on_root


def test_the_stylesheets_hard_code_no_colour_outside_the_token_file() -> None:
    """Rule 1 of the token system, enforced rather than remembered."""
    offenders: dict[str, list[str]] = {}
    for sheet in sorted((PACKAGE_STATIC_DIR / "css").glob("*.css")):
        if sheet.name == "tokens.css":
            continue
        found = re.findall(r"#[0-9a-fA-F]{3,8}\b", sheet.read_text())
        if found:
            offenders[sheet.name] = found
    assert not offenders, offenders
