"""The vendored-asset discipline: every shipped asset has a recorded digest, and no more.

Spec §14: assets are served from the installed package, never from a CDN. That makes the package
the supply chain, so the manifest is checked rather than trusted, and a vendored file with no
entry in `THIRD_PARTY_NOTICES.md` fails here rather than shipping unlicensed.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest

from mirrorwall import PACKAGE_STATIC_DIR

MANIFEST = PACKAGE_STATIC_DIR / "ASSETS.sha256"
NOTICES = Path(__file__).resolve().parents[2] / "THIRD_PARTY_NOTICES.md"


def _recorded() -> dict[str, str]:
    entries: dict[str, str] = {}
    for line in MANIFEST.read_text().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        digest, _, path = line.partition("  ")
        entries[path.strip()] = digest.strip()
    return entries


def _shipped() -> dict[str, str]:
    return {
        f"./{path.relative_to(PACKAGE_STATIC_DIR).as_posix()}": hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for path in sorted(PACKAGE_STATIC_DIR.rglob("*"))
        if path.is_file() and path.name != MANIFEST.name
    }


def test_the_manifest_lists_exactly_what_ships() -> None:
    recorded = _recorded()
    shipped = _shipped()
    assert set(recorded) == set(shipped), {
        "unrecorded": sorted(set(shipped) - set(recorded)),
        "missing": sorted(set(recorded) - set(shipped)),
    }


@pytest.mark.parametrize("relative", sorted(_shipped()))
def test_every_asset_matches_its_recorded_digest(relative: str) -> None:
    assert _shipped()[relative] == _recorded()[relative], relative


def test_every_vendored_file_is_recorded_in_the_third_party_notices() -> None:
    vendor = PACKAGE_STATIC_DIR / "vendor"
    fonts = PACKAGE_STATIC_DIR / "fonts"
    vendored = [
        path
        for root in (vendor, fonts)
        if root.is_dir()
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name != "LICENSE"
    ]
    notices = NOTICES.read_text()
    if not vendored:
        # The current, deliberate state: nothing third-party is vendored, and the notices say so
        # and say why (charts are inline SVG, the font stack degrades, the icons are original).
        assert "**None as of 0.2.0.**" in notices
        return
    for path in vendored:  # pragma: no cover — reached the day something is vendored
        assert path.name in notices, path
        assert (path.parent / "LICENSE").is_file(), f"{path.parent} ships no licence"


def test_no_stylesheet_or_script_reaches_out_to_a_network_origin() -> None:
    """Spec §14: a page load makes no external request."""
    offenders: dict[str, list[str]] = {}
    for path in sorted(PACKAGE_STATIC_DIR.rglob("*")):
        if not path.is_file() or path.suffix not in {".css", ".js", ".svg"}:
            continue
        # An XML namespace URI is an identifier, not a fetch: nothing resolves it at page load.
        text = re.sub(r'xmlns(:\w+)?="[^"]*"', "", path.read_text(encoding="utf-8"))
        found = [
            token for token in ("http://", "https://", "//cdn", "@import url(http") if token in text
        ]
        if found:
            offenders[path.name] = found
    assert not offenders, offenders


def test_the_templates_load_no_external_resource() -> None:
    templates = PACKAGE_STATIC_DIR.parent / "templates"
    for path in sorted(templates.rglob("*.html")):
        text = path.read_text(encoding="utf-8")
        assert "http://" not in text, path
        assert "https://" not in text, path
