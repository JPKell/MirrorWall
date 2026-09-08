"""``table.js``, exercised in a real JavaScript runtime — the same approach as ``test_sse_client``.

Not a transliteration into Python: the shipped file is loaded and run by Node, over a hand-rolled
table (no jsdom in this suite's dependency budget — the fake is a plain object graph shaped exactly
like the DOM surface this module touches: ``tHead``/``tBodies``, ``cells``, ``classList``,
``createElement``). The two properties UI standards §5 names are what is asserted: sorting is
wired only where the server rendered the whole dataset (``data-complete``), and a missing
(em-dash) value sorts last in *both* directions rather than acting like the smallest number.
"""

from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from mirrorwall import PACKAGE_STATIC_DIR

NODE = shutil.which("node") or shutil.which("nodejs")

pytestmark = pytest.mark.skipif(NODE is None, reason="no JavaScript runtime on this machine")

_MODULE_SOURCE = (PACKAGE_STATIC_DIR / "js" / "table.js").read_text()

# The fake DOM. `makeCell`/`makeRow` build the pre-rendered table `table.js` finds already on the
# page (UI standards: server-rendered HTML first, this module only enhances it); `makeElement` is
# what `document.createElement` hands back for the button/details/summary/label/input the module
# builds itself.
_HARNESS = r"""
const store = {};
globalThis.window = globalThis;
window.localStorage = {
  getItem(key) { return Object.prototype.hasOwnProperty.call(store, key) ? store[key] : null; },
  setItem(key, value) { store[key] = value; },
  removeItem(key) { delete store[key]; },
};

function makeElement(tag) {
  return {
    tag: tag,
    _attrs: {},
    _handlers: {},
    children: [],
    textContent: "",
    style: {},
    setAttribute(name, value) { this._attrs[name] = value; },
    getAttribute(name) { return this._attrs[name] ?? null; },
    removeAttribute(name) { delete this._attrs[name]; },
    addEventListener(name, handler) { this._handlers[name] = handler; },
    appendChild(child) { this.children.push(child); return child; },
  };
}

function makeCell(text, classes) {
  const cell = makeElement("td");
  cell.textContent = text;
  cell.hidden = false;
  cell.classList = { contains: (name) => (classes || []).includes(name) };
  return cell;
}

function makeRow(cells) {
  return { cells: cells };
}

globalThis.createdElements = [];
globalThis.document = {
  readyState: "complete",
  createElement(tag) {
    const element = makeElement(tag);
    globalThis.createdElements.push(element);
    return element;
  },
  createTextNode(text) { return { tag: "#text", textContent: text }; },
  querySelectorAll(_selector) { return globalThis.TABLES; },
};

TABLE_SETUP

MODULE_SOURCE

RUN_SCENARIO
"""


def _run(*, table_setup: str, scenario: str) -> dict[str, object]:
    script = (
        _HARNESS.replace("TABLE_SETUP", table_setup)
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


_SORTABLE_TABLE = """
const headerCells = [makeCell("Name"), makeCell("Score", ["numeric"])];
const bodyRows = [
  makeRow([makeCell("Alpha"), makeCell("10")]),
  makeRow([makeCell("Beta"), makeCell("—")]),
  makeRow([makeCell("Gamma"), makeCell("5")]),
];
const body = {
  rows: bodyRows,
  appendChild(row) {
    const at = this.rows.indexOf(row);
    if (at !== -1) { this.rows.splice(at, 1); }
    this.rows.push(row);
  },
};
globalThis.TABLE = {
  _attrs: { "data-table": "scores", "data-sortable": "true", "data-complete": "true" },
  getAttribute(name) { return this._attrs[name] ?? null; },
  tHead: { rows: [{ cells: headerCells }] },
  tBodies: [body],
  parentNode: { insertBefore() {} },
};
globalThis.TABLES = [globalThis.TABLE];
"""


def test_a_table_missing_columns_is_not_wired_for_client_side_sorting() -> None:
    """UI standards §5: only a table holding the whole dataset gets a client-side sort control."""
    setup = _SORTABLE_TABLE.replace('"data-complete": "true"', '"data-complete": "false"')
    result = _run(
        table_setup=setup,
        scenario="""
console.log(JSON.stringify({
  buttons: createdElements.filter((el) => el.tag === "button").length,
}));
""",
    )
    assert result["buttons"] == 0


def test_sorting_ascending_puts_the_missing_value_last_not_first() -> None:
    result = _run(
        table_setup=_SORTABLE_TABLE,
        scenario="""
const button = createdElements.find((el) => el.tag === "button" && el.textContent === "Score");
button._handlers.click();
console.log(JSON.stringify({
  order: TABLE.tBodies[0].rows.map((row) => row.cells[0].textContent),
  ariaSort: TABLE.tHead.rows[0].cells[1].getAttribute("aria-sort"),
}));
""",
    )
    assert result["order"] == ["Gamma", "Alpha", "Beta"]
    assert result["ariaSort"] == "ascending"


def test_sorting_descending_still_puts_the_missing_value_last() -> None:
    """The source's own comment: the missing case is pre-flipped, so it stays last either way."""
    result = _run(
        table_setup=_SORTABLE_TABLE,
        scenario="""
const button = createdElements.find((el) => el.tag === "button" && el.textContent === "Score");
button._handlers.click();
button._handlers.click();
console.log(JSON.stringify({
  order: TABLE.tBodies[0].rows.map((row) => row.cells[0].textContent),
  ariaSort: TABLE.tHead.rows[0].cells[1].getAttribute("aria-sort"),
}));
""",
    )
    assert result["order"] == ["Alpha", "Gamma", "Beta"]
    assert result["ariaSort"] == "descending"


_WIDE_TABLE = """
function wideCell(text) { return makeCell(text); }
const headerCells = [
  wideCell("A"), wideCell("B"), wideCell("C"), wideCell("D"), wideCell("E"), wideCell("F"),
];
const bodyRow = makeRow(headerCells.map((_c, i) => wideCell("r" + i)));
const body = { rows: [bodyRow], appendChild() {} };
globalThis.TABLE = {
  _attrs: { "data-table": "wide" },
  getAttribute(name) { return this._attrs[name] ?? null; },
  tHead: { rows: [{ cells: headerCells }] },
  tBodies: [body],
  parentNode: { insertBefore(node) { globalThis.insertedBefore = node; } },
};
globalThis.TABLES = [globalThis.TABLE];
"""


def test_a_wide_table_gets_a_column_visibility_control_that_persists_the_choice() -> None:
    """Six or more columns (UI standards) gets a "Columns" control, independent of sortability."""
    result = _run(
        table_setup=_WIDE_TABLE,
        scenario="""
const details = createdElements.find((el) => el.tag === "details");
const inputs = createdElements.filter((el) => el.tag === "input");
// Hide column 2 ("C"), the way a reader clicking its checkbox would.
inputs[2].checked = false;
inputs[2]._handlers.change();
console.log(JSON.stringify({
  detailsInserted: insertedBefore === details,
  headerHidden: TABLE.tHead.rows[0].cells.map((c) => !!c.hidden),
  bodyHidden: TABLE.tBodies[0].rows[0].cells.map((c) => !!c.hidden),
  stored: JSON.parse(store["mirrorwall-columns:wide"]),
}));
""",
    )
    assert result["detailsInserted"] is True
    assert result["headerHidden"] == [False, False, True, False, False, False]
    assert result["bodyHidden"] == [False, False, True, False, False, False]
    assert result["stored"] == [2]


def test_a_previously_hidden_column_is_restored_from_storage_on_the_next_load() -> None:
    setup = "store['mirrorwall-columns:wide'] = JSON.stringify([1]);\n" + _WIDE_TABLE
    result = _run(
        table_setup=setup,
        scenario="""
console.log(JSON.stringify({
  headerHidden: TABLE.tHead.rows[0].cells.map((c) => !!c.hidden),
  checkboxChecked: createdElements.filter((el) => el.tag === "input").map((el) => el.checked),
}));
""",
    )
    assert result["headerHidden"] == [False, True, False, False, False, False]
    assert result["checkboxChecked"] == [True, False, True, True, True, True]
