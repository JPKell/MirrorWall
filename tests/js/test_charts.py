"""``charts.js``: reads `data-echarts`, themes it from tokens, redraws on theme change (ADR-0142).

Same fake-DOM approach as ``test_log_pane.py``: enough of the platform to prove the module's own
logic — parsing, wiring, re-theming — not a browser and not ECharts itself, which is stubbed.
"""

from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from mirrorwall import PACKAGE_STATIC_DIR

NODE = shutil.which("node") or shutil.which("nodejs")

_MODULE_SOURCE = (PACKAGE_STATIC_DIR / "js" / "charts.js").read_text()

# One `[data-echarts]` element and a fake `echarts.init` recording every `setOption` call, so a
# test can inspect what this module themed without ECharts ever drawing anything real. Token
# colours come from a fake `getComputedStyle` keyed by custom-property name, same contract as the
# real one (`style.getPropertyValue(name)`).
_HARNESS = r"""
function makeElement(dataEcharts) {
  return {
    _attrs: { "data-echarts": dataEcharts },
    getAttribute(name) {
      return Object.prototype.hasOwnProperty.call(this._attrs, name) ? this._attrs[name] : null;
    },
  };
}

const TOKENS = {
  "--mw-chart-1": "#2F80ED", "--mw-chart-2": "#0E8074", "--mw-chart-3": "#6D3FD1",
  "--mw-chart-4": "#8A5300", "--mw-chart-5": "#B3261E", "--mw-chart-6": "#157F3C",
  "--mw-text-muted": "#5A6675",
};
globalThis.getComputedStyle = function () {
  return { getPropertyValue: (name) => TOKENS[name] || "" };
};

const instances = [];
function makeInstance() {
  const instance = {
    calls: [],
    setOption(option, notMerge) { this.calls.push({ option, notMerge }); },
  };
  instances.push(instance);
  return instance;
}
globalThis.window = globalThis;
window.echarts = { init: () => makeInstance() };

const elements = ELEMENTS;
globalThis.document = {
  readyState: "complete",
  _handlers: {},
  querySelectorAll(selector) { return selector === "[data-echarts]" ? elements : []; },
  addEventListener(name, handler) { this._handlers[name] = handler; },
};

MODULE_SOURCE

RUN_SCENARIO
"""


def _run(elements_js: str, scenario: str) -> dict[str, object]:
    script = (
        _HARNESS.replace("MODULE_SOURCE", _MODULE_SOURCE)
        .replace("ELEMENTS", elements_js)
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


@pytest.mark.skipif(NODE is None, reason="no JavaScript runtime on this machine")
def test_a_chart_is_themed_from_tokens_at_wire_time() -> None:
    result = _run(
        '[makeElement(JSON.stringify({series: [{type: "line", data: [1, 2, 3]}]}))]',
        """
const call = instances[0].calls[0];
console.log(JSON.stringify({
  colour: call.option.color,
  background: call.option.backgroundColor,
  textColour: call.option.textStyle.color,
  seriesKept: call.option.series[0].type,
  notMerge: call.notMerge,
}));
""",
    )
    assert result == {
        "colour": ["#2F80ED", "#0E8074", "#6D3FD1", "#8A5300", "#B3261E", "#157F3C"],
        "background": "transparent",
        "textColour": "#5A6675",
        "seriesKept": "line",
        "notMerge": True,
    }


@pytest.mark.skipif(NODE is None, reason="no JavaScript runtime on this machine")
def test_a_theme_change_redraws_every_wired_chart() -> None:
    result = _run(
        "[makeElement(JSON.stringify({series: []})), makeElement(JSON.stringify({series: []}))]",
        """
document._handlers["mirrorwall:themechange"]();
console.log(JSON.stringify({ calls: instances.map((i) => i.calls.length) }));
""",
    )
    assert result == {"calls": [2, 2]}


@pytest.mark.skipif(NODE is None, reason="no JavaScript runtime on this machine")
def test_malformed_option_json_is_skipped_not_thrown() -> None:
    result = _run(
        "[makeElement('not json'), makeElement(JSON.stringify({series: []}))]",
        """
console.log(JSON.stringify({ instancesCreated: instances.length }));
""",
    )
    assert result == {"instancesCreated": 1}


@pytest.mark.skipif(NODE is None, reason="no JavaScript runtime on this machine")
def test_an_element_with_no_data_echarts_is_left_alone() -> None:
    result = _run(
        "[makeElement(null)]",
        """
console.log(JSON.stringify({ instancesCreated: instances.length }));
""",
    )
    assert result == {"instancesCreated": 0}
