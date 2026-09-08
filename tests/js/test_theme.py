"""``theme.js``, exercised in a real JavaScript runtime — the same approach as ``test_sse_client``.

Not a transliteration into Python: the shipped file is loaded and run by Node, with a minimal
``document``/``window`` stubbed in by hand (no jsdom in this suite's dependency budget). The
properties asserted are UI standards §9's: a choice applies without a reload, survives to the next
page load, and tells anything drawing with token colours to redraw — plus the private-mode
fallback the module's own comments name (ADR-0016's sibling concern on the client: a storage
failure must not stop the choice from applying to the page in front of the reader).
"""

from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from mirrorwall import PACKAGE_STATIC_DIR

NODE = shutil.which("node") or shutil.which("nodejs")

pytestmark = pytest.mark.skipif(NODE is None, reason="no JavaScript runtime on this machine")

_MODULE_SOURCE = (PACKAGE_STATIC_DIR / "js" / "theme.js").read_text()

# A hand-rolled DOM: a `<select data-theme-select>`, `<html>` (via `documentElement`), a
# `localStorage` backed by a plain object, and a `CustomEvent` that records what fires. Enough of
# the surface `theme.js` touches to run it, no more.
_HARNESS = r"""
const store = {};
globalThis.window = globalThis;
window.localStorage = {
  getItem(key) { return Object.prototype.hasOwnProperty.call(store, key) ? store[key] : null; },
  setItem(key, value) { store[key] = value; },
  removeItem(key) { delete store[key]; },
};

const dispatched = [];
class FakeCustomEvent {
  constructor(type, init) { this.type = type; this.detail = (init || {}).detail; }
}
globalThis.CustomEvent = FakeCustomEvent;

const htmlAttrs = {};
const select = {
  value: "system",
  _handlers: {},
  _dataAttrs: {},
  getAttribute(name) { return this._dataAttrs[name] ?? null; },
  addEventListener(name, handler) { this._handlers[name] = handler; },
};

globalThis.document = {
  readyState: "complete",
  documentElement: {
    setAttribute(name, value) { htmlAttrs[name] = value; },
    removeAttribute(name) { delete htmlAttrs[name]; },
  },
  querySelector(_selector) { return select; },
  addEventListener() {},
  dispatchEvent(event) { dispatched.push(event); },
};

STORE_SEED

MODULE_SOURCE

RUN_SCENARIO
"""


def _run(*, seed: dict[str, str] | None, scenario: str) -> dict[str, object]:
    store_seed = "\n".join(
        f"store[{json.dumps(key)}] = {json.dumps(value)};" for key, value in (seed or {}).items()
    )
    script = (
        _HARNESS.replace("STORE_SEED", store_seed)
        .replace("MODULE_SOURCE", _MODULE_SOURCE)
        .replace("RUN_SCENARIO", scenario)
    )
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


def test_choosing_a_theme_applies_it_persists_it_and_announces_the_change() -> None:
    result = _run(
        seed=None,
        scenario="""
select.value = "dark";
select._handlers.change();
console.log(JSON.stringify({
  attr: htmlAttrs["data-theme"],
  stored: store["mirrorwall-theme"],
  eventType: dispatched[dispatched.length - 1].type,
  eventDetail: dispatched[dispatched.length - 1].detail,
}));
""",
    )
    assert result["attr"] == "dark"
    assert result["stored"] == "dark"
    assert result["eventType"] == "mirrorwall:themechange"
    assert result["eventDetail"] == {"theme": "dark"}


def test_choosing_system_clears_the_attribute_and_the_stored_choice() -> None:
    """ "system" is not a fourth theme to remember — it is the absence of an override."""
    result = _run(
        seed={"mirrorwall-theme": "dark"},
        scenario="""
select.value = "system";
select._handlers.change();
console.log(JSON.stringify({
  hasAttr: Object.prototype.hasOwnProperty.call(htmlAttrs, "data-theme"),
  hasStored: Object.prototype.hasOwnProperty.call(store, "mirrorwall-theme"),
}));
""",
    )
    assert result["hasAttr"] is False
    assert result["hasStored"] is False


def test_a_stored_choice_is_restored_as_the_select_value_on_the_next_load() -> None:
    result = _run(
        seed={"mirrorwall-theme": "dark"},
        scenario="console.log(JSON.stringify({restored: select.value}));",
    )
    assert result["restored"] == "dark"


def test_an_unrecognised_stored_value_falls_back_to_system_rather_than_erroring() -> None:
    result = _run(
        seed={"mirrorwall-theme": "not-a-real-theme"},
        scenario="console.log(JSON.stringify({restored: select.value}));",
    )
    assert result["restored"] == "system"


def test_a_storage_failure_still_lets_the_choice_apply_to_this_page_view() -> None:
    """Private-mode `localStorage` throws; the module's own comment says the page still works."""
    result = _run(
        seed=None,
        scenario="""
window.localStorage.getItem = () => { throw new Error("blocked"); };
window.localStorage.setItem = () => { throw new Error("blocked"); };
select.value = "dark";
select._handlers.change();
console.log(JSON.stringify({ attr: htmlAttrs["data-theme"] }));
""",
    )
    assert result["attr"] == "dark"
