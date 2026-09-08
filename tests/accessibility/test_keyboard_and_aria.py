"""Phase 3's accessibility pass: keyboard traversal, focus management, reduced motion, skip link.

``tests/snapshot/test_components.py`` already proves every component's static markup carries the
ARIA its pattern requires; what it cannot prove is the *behaviour* — that ``drawer.js``'s
hand-rolled focus trap actually cycles focus inside the drawer and gives it back to whatever
opened it. That module is the one piece of interactive keyboard handling this package writes
itself (``dialog.js`` delegates entirely to the platform's own ``<dialog>`` element, which is
exactly why it needs no test here). This file covers that trap, the skip link's target, and the
reduced-motion rule the CSS carries.
"""

from __future__ import annotations

import json
import shutil
import subprocess

import pytest
from jinja2 import Environment

from mirrorwall import PACKAGE_STATIC_DIR

NODE = shutil.which("node") or shutil.which("nodejs")

_MODULE_SOURCE = (PACKAGE_STATIC_DIR / "js" / "drawer.js").read_text()

# A fake DOM: a drawer with three focusable children (first, middle, last), a trigger, and a
# `document.activeElement`/`focus()` pair wired together the way a real browser's are — enough to
# prove the trap without a real one.
_HARNESS = r"""
function makeElement(tag) {
  return {
    tag: tag, _attrs: {}, _handlers: {}, children: [], hidden: false,
    setAttribute(name, value) { this._attrs[name] = value; },
    getAttribute(name) { return this._attrs[name] ?? null; },
    addEventListener(name, handler) { this._handlers[name] = handler; },
    focus() { globalThis.document.activeElement = this; },
    querySelectorAll(selector) {
      // Only ever called with the focusable-elements selector or the close-button selector.
      if (selector.indexOf("data-drawer-close") !== -1) { return this._closeButtons || []; }
      return this._focusable || [];
    },
  };
}

const first = makeElement("a");
const middle = makeElement("button");
const last = makeElement("input");
const drawer = makeElement("div");
drawer.className = "drawer";
drawer.hidden = true;
drawer._focusable = [first, middle, last];

const trigger = makeElement("button");
trigger.getAttribute = () => "the-drawer";

globalThis.document = {
  readyState: "complete",
  activeElement: null,
  getElementById(id) { return id === "the-drawer" ? drawer : null; },
  querySelectorAll(selector) {
    if (selector === "[data-drawer-open]") { return [trigger]; }
    if (selector === ".drawer") { return [drawer]; }
    return [];
  },
};

MODULE_SOURCE

trigger._handlers.click();
const afterOpen = { hidden: drawer.hidden, active: document.activeElement === first };

RUN_SCENARIO
"""


def _run(scenario: str) -> dict[str, object]:
    script = _HARNESS.replace("MODULE_SOURCE", _MODULE_SOURCE).replace("RUN_SCENARIO", scenario)
    assert NODE is not None
    completed = subprocess.run(  # noqa: S603 — fixed argv, script supplied on stdin
        [NODE, "--input-type=module", "-e", script],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    result: dict[str, object] = json.loads(completed.stdout.strip().splitlines()[-1])
    return result


@pytest.mark.skipif(NODE is None, reason="no JavaScript runtime on this machine")
def test_opening_the_drawer_focuses_its_first_focusable_element() -> None:
    result = _run("console.log(JSON.stringify({ afterOpen: afterOpen }));")
    assert result["afterOpen"] == {"hidden": False, "active": True}


@pytest.mark.skipif(NODE is None, reason="no JavaScript runtime on this machine")
def test_escape_closes_the_drawer_and_returns_focus_to_its_trigger() -> None:
    result = _run(
        """
drawer._handlers.keydown({ key: "Escape" });
console.log(JSON.stringify({
  hidden: drawer.hidden,
  focusReturnedToTrigger: document.activeElement === trigger,
}));
"""
    )
    assert result["hidden"] is True
    assert result["focusReturnedToTrigger"] is True


@pytest.mark.skipif(NODE is None, reason="no JavaScript runtime on this machine")
def test_tab_from_the_last_element_wraps_to_the_first() -> None:
    result = _run(
        """
last.focus();
let prevented = false;
const onPrevent = () => { prevented = true; };
drawer._handlers.keydown({ key: "Tab", shiftKey: false, preventDefault: onPrevent });
console.log(JSON.stringify({ wrapped: document.activeElement === first, prevented: prevented }));
"""
    )
    assert result["wrapped"] is True
    assert result["prevented"] is True


@pytest.mark.skipif(NODE is None, reason="no JavaScript runtime on this machine")
def test_shift_tab_from_the_first_element_wraps_to_the_last() -> None:
    result = _run(
        """
first.focus();
let prevented = false;
const onPrevent = () => { prevented = true; };
drawer._handlers.keydown({ key: "Tab", shiftKey: true, preventDefault: onPrevent });
console.log(JSON.stringify({ wrapped: document.activeElement === last, prevented: prevented }));
"""
    )
    assert result["wrapped"] is True
    assert result["prevented"] is True


@pytest.mark.skipif(NODE is None, reason="no JavaScript runtime on this machine")
def test_tab_in_the_middle_of_the_drawer_is_left_alone() -> None:
    """The trap only intervenes at the boundary — anywhere else, native Tab order is correct."""
    result = _run(
        """
middle.focus();
let prevented = false;
const onPrevent = () => { prevented = true; };
drawer._handlers.keydown({ key: "Tab", shiftKey: false, preventDefault: onPrevent });
console.log(JSON.stringify({
  stillOnMiddle: document.activeElement === middle,
  prevented: prevented,
}));
"""
    )
    assert result["stillOnMiddle"] is True
    assert result["prevented"] is False


def test_the_skip_link_targets_the_main_content_landmark(environment: Environment) -> None:
    """A skip link that points nowhere is worse than none: it announces a promise it breaks."""
    html = environment.get_template("mirrorwall/base.html").render(nav_items=[], page=None)
    assert '<a class="skip-link" href="#content">' in html
    assert 'id="content"' in html


def test_reduced_motion_disables_transitions_and_animations() -> None:
    """UI standards accessibility pass: `prefers-reduced-motion` is honoured, not just declared."""
    reset_css = (PACKAGE_STATIC_DIR / "css" / "reset.css").read_text()
    assert "@media (prefers-reduced-motion: reduce)" in reset_css
    block = reset_css.split("prefers-reduced-motion: reduce)", 1)[1]
    assert "transition: none" in block
    assert "animation: none" in block
