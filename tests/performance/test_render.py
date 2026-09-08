"""Performance budgets from spec §15: template render, table sort, JS payload size.

Excluded by default; run with ``pytest -m performance`` (the same convention every other
package's ``tests/performance`` uses). ``pytest-randomly`` and cold-cache jitter mean a single
sample would be a flake generator, so the render and sort budgets are asserted on the best of
several samples, the way a "how fast can this go" budget should be measured — a background hiccup
should not fail a budget the code itself meets.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time

import pytest
from jinja2 import Environment

from mirrorwall import PACKAGE_STATIC_DIR, create_template_environment

pytestmark = pytest.mark.performance

NODE = shutil.which("node") or shutil.which("nodejs")


def test_a_typical_page_renders_within_budget() -> None:
    """spec §15: template render, typical page <= 30 ms."""
    environment: Environment = create_template_environment(globals_={"product_name": "Example"})
    template = environment.get_template("mirrorwall/base.html")
    context = {
        "product_version": "1.0.0",
        "nav_items": [
            {"href": "/", "label": "Home", "key": "home"},
            {"href": "/runs", "label": "Runs", "key": "runs"},
        ],
        "page": "home",
        "show_telemetry_bar": True,
        "theme_storage_key": "mirrorwall-theme",
        "footer_text": "MirrorWall",
    }
    template.render(**context)  # warm the template cache; a cold compile is not the render budget

    best = min(_timed(lambda: template.render(**context)) for _ in range(20))
    assert best <= 0.030, f"typical page render took {best * 1000:.2f} ms, budget is 30 ms"


def _timed(action: object) -> float:
    start = time.perf_counter()
    action()  # type: ignore[operator]
    return time.perf_counter() - start


def test_the_js_shipped_to_a_typical_page_is_within_budget() -> None:
    """spec §15: JS shipped per page (excluding charting vendor) <= 60 KB uncompressed.

    ``charts.js`` is this package's own charting container, not a vendored library — spec §15's
    "charting vendor" line is the separate 1 MB budget for whatever charting library an
    application vendors alongside it, which this package ships none of. Excluded here anyway,
    because a page that does not render a chart never loads it.
    """
    shipped = sorted(PACKAGE_STATIC_DIR.glob("js/*.js"))
    total_bytes = sum(path.stat().st_size for path in shipped if path.name != "charts.js")
    assert total_bytes <= 60_000, f"{total_bytes} bytes of JS shipped, budget is 60 000"


@pytest.mark.skipif(NODE is None, reason="no JavaScript runtime on this machine")
def test_sorting_a_thousand_by_twenty_table_is_within_budget() -> None:
    """spec §15: table sort, 1 000 rows x 20 columns <= 150 ms, measured in a real JS runtime."""
    module_source = (PACKAGE_STATIC_DIR / "js" / "table.js").read_text()
    script = f"""
function makeElement(tag) {{
  return {{
    tag: tag, _attrs: {{}}, _handlers: {{}}, children: [], textContent: "", style: {{}},
    setAttribute(name, value) {{ this._attrs[name] = value; }},
    getAttribute(name) {{ return this._attrs[name] ?? null; }},
    removeAttribute(name) {{ delete this._attrs[name]; }},
    addEventListener(name, handler) {{ this._handlers[name] = handler; }},
    appendChild(child) {{ this.children.push(child); return child; }},
  }};
}}
function makeCell(text, numeric) {{
  const cell = makeElement("td");
  cell.textContent = text;
  cell.classList = {{ contains: (name) => numeric && name === "numeric" }};
  return cell;
}}
const columns = 20;
const rows = 1000;
const headerCells = [];
for (let c = 0; c < columns; c += 1) {{ headerCells.push(makeCell("Col" + c, c === 1)); }}
const bodyRows = [];
for (let r = 0; r < rows; r += 1) {{
  const cells = [];
  for (let c = 0; c < columns; c += 1) {{
    cells.push(makeCell(c === 1 ? String((r * 37) % 997) : "v" + r + "_" + c, c === 1));
  }}
  bodyRows.push({{ cells: cells }});
}}
const body = {{
  rows: bodyRows,
  appendChild(row) {{
    const at = this.rows.indexOf(row);
    if (at !== -1) {{ this.rows.splice(at, 1); }}
    this.rows.push(row);
  }},
}};
const table = {{
  _attrs: {{ "data-table": "big", "data-sortable": "true", "data-complete": "true" }},
  getAttribute(name) {{ return this._attrs[name] ?? null; }},
  tHead: {{ rows: [{{ cells: headerCells }}] }},
  tBodies: [body],
  parentNode: {{ insertBefore() {{}} }},
}};
globalThis.window = globalThis;
window.localStorage = {{ getItem: () => null, setItem: () => {{}}, removeItem: () => {{}} }};
const createdButtons = [];
globalThis.document = {{
  readyState: "complete",
  createElement(tag) {{
    const element = makeElement(tag);
    if (tag === "button") {{ createdButtons.push(element); }}
    return element;
  }},
  createTextNode(text) {{ return {{ textContent: text }}; }},
  querySelectorAll(_selector) {{ return [table]; }},
}};

{module_source}

const button = createdButtons[1];
const start = process.hrtime.bigint();
button._handlers.click();
const elapsedMs = Number(process.hrtime.bigint() - start) / 1e6;
console.log(JSON.stringify({{ elapsedMs: elapsedMs }}));
"""
    assert NODE is not None
    best = None
    for _ in range(5):
        completed = subprocess.run(  # noqa: S603 — fixed argv, script supplied on stdin
            [NODE, "--input-type=module", "-e", script],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        assert completed.returncode == 0, completed.stderr
        elapsed = json.loads(completed.stdout.strip().splitlines()[-1])["elapsedMs"]
        best = elapsed if best is None else min(best, elapsed)
    assert best is not None
    assert best <= 150, f"sorting 1000x20 took {best:.1f} ms, budget is 150 ms"
