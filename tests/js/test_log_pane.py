"""``log_pane.js``: the bounded buffer and the pause button (design brief §5, ADR-0128 rule 6).

The same fake-DOM approach as ``tests/accessibility/test_keyboard_and_aria.py``'s drawer harness:
enough of the platform to prove the module's own logic, not a browser. ``MutationObserver`` is
stubbed to capture its callback rather than fire it on a timer, so a test triggers a "mutation"
deterministically instead of racing a real one.
"""

from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from mirrorwall import PACKAGE_STATIC_DIR

NODE = shutil.which("node") or shutil.which("nodejs")

_MODULE_SOURCE = (PACKAGE_STATIC_DIR / "js" / "log_pane.js").read_text()

# A pane with a bounded body: `body._lines` is the live array `querySelectorAll` reads from, and
# each fake line's `remove()` splices itself out — the one behaviour the module actually depends
# on. `MutationObserver` is captured rather than wired to anything real: the test decides when a
# "mutation" happened by calling `global.__observed()` itself.
_HARNESS = r"""
function makeLine() {
  const line = {
    tag: "div",
    remove() {
      const index = body._lines.indexOf(line);
      if (index !== -1) { body._lines.splice(index, 1); }
    },
  };
  return line;
}

function makeElement(tag) {
  return {
    tag: tag, _attrs: {}, _handlers: {},
    setAttribute(name, value) { this._attrs[name] = value; },
    getAttribute(name) { return this._attrs[name] ?? null; },
    addEventListener(name, handler) { this._handlers[name] = handler; },
  };
}

const body = makeElement("div");
body.className = "log-pane-body";
body._lines = [];
body.querySelectorAll = function (selector) {
  if (selector === ".log-pane-line") { return body._lines.slice(); }
  return [];
};

const droppedFrame = makeElement("span");
droppedFrame.hidden = true;
const droppedCount = makeElement("span");
droppedCount.textContent = "0";
const pauseButton = makeElement("button");
pauseButton.textContent = "Pause";

const pane = makeElement("div");
pane.getAttribute = (name) => (name === "data-max-lines" ? "3" : null);
pane.querySelector = function (selector) {
  if (selector === ".log-pane-body") { return body; }
  if (selector === "[data-log-pane-dropped]") { return droppedFrame; }
  if (selector === "[data-log-pane-dropped-count]") { return droppedCount; }
  if (selector === "[data-log-pane-pause]") { return pauseButton; }
  return null;
};

globalThis.MutationObserver = function (callback) {
  this.observe = function () { globalThis.__observed = () => callback([], this); };
};

globalThis.document = {
  readyState: "complete",
  body: makeElement("body"),
  querySelectorAll(selector) { return selector === "[data-log-pane]" ? [pane] : []; },
};

MODULE_SOURCE

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
def test_lines_beyond_max_are_removed_and_counted_as_dropped() -> None:
    result = _run(
        """
for (let i = 0; i < 5; i += 1) { body._lines.push(makeLine()); }
__observed();
console.log(JSON.stringify({
  remaining: body._lines.length,
  dropped: droppedCount.textContent,
  frameShown: droppedFrame.hidden === false,
}));
"""
    )
    assert result == {"remaining": 3, "dropped": "2", "frameShown": True}


@pytest.mark.skipif(NODE is None, reason="no JavaScript runtime on this machine")
def test_a_pane_within_budget_is_left_alone() -> None:
    result = _run(
        """
body._lines.push(makeLine(), makeLine());
__observed();
console.log(JSON.stringify({
  remaining: body._lines.length,
  frameShown: droppedFrame.hidden === false,
}));
"""
    )
    assert result == {"remaining": 2, "frameShown": False}


@pytest.mark.skipif(NODE is None, reason="no JavaScript runtime on this machine")
def test_the_pause_button_toggles_its_own_state() -> None:
    result = _run(
        """
function pauseState() {
  return { pressed: pauseButton.getAttribute("aria-pressed"), label: pauseButton.textContent };
}
pauseButton._handlers.click();
const afterFirstClick = pauseState();
pauseButton._handlers.click();
const afterSecondClick = pauseState();
console.log(JSON.stringify({ afterFirstClick, afterSecondClick }));
"""
    )
    assert result["afterFirstClick"] == {"pressed": "true", "label": "Resume"}
    assert result["afterSecondClick"] == {"pressed": "false", "label": "Pause"}


@pytest.mark.skipif(NODE is None, reason="no JavaScript runtime on this machine")
def test_a_paused_pane_declines_the_next_htmx_swap() -> None:
    """ADR-0128 rule 6: pause is a display choice — the SSE connection itself is untouched."""
    result = _run(
        """
pauseButton._handlers.click(); // pressed
function closesToPane(selector) { return selector === "[data-log-pane]" ? pane : null; }
const event = { target: { closest: closesToPane }, detail: {} };
document.body._handlers["htmx:beforeSwap"](event);
console.log(JSON.stringify({ shouldSwap: event.detail.shouldSwap }));
"""
    )
    assert result["shouldSwap"] is False


@pytest.mark.skipif(NODE is None, reason="no JavaScript runtime on this machine")
def test_an_unpaused_pane_leaves_the_swap_decision_alone() -> None:
    result = _run(
        """
function closesToPane(selector) { return selector === "[data-log-pane]" ? pane : null; }
const event = { target: { closest: closesToPane }, detail: {} };
document.body._handlers["htmx:beforeSwap"](event);
console.log(JSON.stringify({ shouldSwapUntouched: !("shouldSwap" in event.detail) }));
"""
    )
    assert result["shouldSwapUntouched"] is True
