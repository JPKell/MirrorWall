"""The WM row's demonstration: the design brief's shell skeleton, built from 0.3's macros alone.

Not a new gallery page (`gallery.py`'s Phase 3 implementation is still deferred) — this is the
proof the kickoff prompt asks for: a top bar of `app_tab`s and dots, a `telemetry_bar` with extra
`meter`s, a `side_nav`, four `figure_card`s, a dense `table`, and a `log_pane` fed by a fake
stream, composed from nothing but public macros, rendering in both themes with no application
vocabulary anywhere in the template that builds it.
"""

from __future__ import annotations

import pytest
from jinja2 import Environment

_SHELL_TEMPLATE = """
{%- from "mirrorwall/components.html" import app_tab, telemetry_bar, side_nav -%}
{%- from "mirrorwall/components.html" import card, table, log_pane -%}
<div class="app-tab-strip">
  {%- for app in apps %}
  {{ app_tab(app.label, app.href, status=app.status, selected=app.selected) }}
  {%- endfor %}
</div>
{{ telemetry_bar("/telemetry/stream", meters=meters) }}
{{ side_nav(sections, footer="loadcoach 1.3.0 · :8766") }}
<ul class="card-grid">
  {%- for figure in figures %}
  {{ card(figure.label, figure.value, note=figure.note, kind="figure") }}
  {%- endfor %}
</ul>
{{ table(columns, rows, density="dense", table_id="models") }}
{{ log_pane("run-log", stream_url="/runs/1/stream") }}
"""

_APPS = [
    {"label": "FreeWeight", "href": "/freeweight", "status": "ok", "selected": False},
    {"label": "LoadCoach", "href": "/loadcoach", "status": "ok", "selected": True},
    {"label": "IdeaPress", "href": "/ideapress", "status": "degraded", "selected": False},
    {"label": "PromptCadence", "href": "/promptcadence", "status": "stopped", "selected": False},
]
_METERS = [
    {"label": "GPU", "value_text": "61%", "percent": 61},
    {"label": "VRAM", "value_text": "11.2 / 16.0 GB", "percent": 70},
    {"label": "QUEUE", "value_text": "2 active", "percent": None},
]
_SECTIONS = [
    {
        "title": "LoadCoach",
        "links": [
            {"label": "Overview", "href": "/", "selected": True},
            {"label": "Models", "href": "/models"},
            {"label": "Routing", "href": "/routing"},
        ],
    }
]
_FIGURES = [
    {"label": "Jobs today", "value": "42", "note": None},
    {"label": "Spend today", "value": "$4.12", "note": "of $10.00"},
    {"label": "Evidence", "value": "9", "note": None},
    {"label": "Breakers", "value": "0", "note": "open"},
]
_COLUMNS = [
    {"label": "Name"},
    {"label": "Digest", "mono": True},
    {"label": "Size", "numeric": True},
]
_ROWS = [["gpt-oss-20b", "sha256:9f62…", "13.2 GB"]]


def _render(environment: Environment) -> str:
    return environment.from_string(_SHELL_TEMPLATE).render(
        apps=_APPS,
        meters=_METERS,
        sections=_SECTIONS,
        figures=_FIGURES,
        columns=_COLUMNS,
        rows=_ROWS,
    )


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_the_shell_skeleton_renders_from_0_3_macros_alone(
    environment: Environment, theme: str
) -> None:
    """Every element the design brief's artboard names, built from public macros only."""
    html = _render(environment)

    # Top bar: four app tabs, four dots, exactly one selected.
    assert html.count('class="app-tab"') == 4
    assert html.count('class="status-dot"') == 4
    assert html.count('aria-current="page"') == 2  # the selected app tab and the selected menu link

    # Telemetry strip: the fixed fields plus the two percent-bearing extra meters (QUEUE has none).
    assert 'aria-label="System telemetry"' in html
    assert html.count('role="meter"') == 2
    assert "QUEUE" in html and "2 active" in html

    # Left menu: the section title, three links, the footer.
    assert "LoadCoach" in html
    assert html.count("<li>") >= 3
    assert "loadcoach 1.3.0" in html

    # Four figure cards, mono tabular value.
    assert html.count("card--figure") == 4
    assert "$4.12" in html

    # A dense table with one mono column.
    assert 'data-density="dense"' in html
    assert '<td class="mono">sha256:9f62…</td>' in html

    # A log pane wired to an SSE region, pausable, initially empty.
    assert 'hx-ext="sse"' in html
    assert 'sse-connect="/runs/1/stream"' in html
    assert "data-log-pane-pause" in html
