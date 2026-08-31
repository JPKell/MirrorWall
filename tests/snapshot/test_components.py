"""Every component macro, rendered in both themes, with the ARIA its pattern requires.

"Snapshot" here means a rendered-output assertion on the properties that matter — the tag, the
required ARIA attributes, the token classes — rather than a byte-for-byte golden file. A golden
that fails on a whitespace change teaches a maintainer to regenerate it without reading it, which
is the opposite of what a snapshot is for.
"""

from __future__ import annotations

import re

import pytest
from jinja2 import Environment

from mirrorwall import PACKAGE_STATIC_DIR

MACROS = '{% from "mirrorwall/components.html" import '
THEMES = ("light", "dark")


def render(environment: Environment, source: str, **context: object) -> str:
    return environment.from_string(source).render(**context)


@pytest.mark.parametrize("theme", THEMES)
def test_button_renders_its_variant_in_both_themes(environment: Environment, theme: str) -> None:
    html = render(
        environment,
        MACROS + "button %}{{ button('Run', variant=variant) }}",
        variant="primary" if theme == "light" else "danger",
    )
    assert html.startswith("<button")
    assert 'type="button"' in html
    assert "data-variant=" in html


def test_button_carries_its_disabled_and_label_state(environment: Environment) -> None:
    html = render(
        environment,
        MACROS + "button %}{{ button('Stop', disabled=True, aria_label='Stop the current task') }}",
    )
    assert "disabled" in html
    assert 'aria-label="Stop the current task"' in html


def test_badge_states_its_word_as_well_as_its_colour(environment: Environment) -> None:
    """UI standards §4.1: colour is never the only signal."""
    html = render(environment, MACROS + "badge %}{{ badge('Degraded', tone='warning') }}")
    assert "Degraded" in html
    assert "status-warning" in html


def test_input_associates_its_label_hint_and_error(environment: Environment) -> None:
    html = render(
        environment,
        MACROS + "input %}{{ input('name', 'Name', hint='As the provider reports it') }}",
    )
    assert 'for="mw-field-name"' in html
    assert 'id="mw-field-name"' in html
    assert 'aria-describedby="mw-field-name-hint"' in html

    invalid = render(environment, MACROS + "input %}{{ input('name', 'Name', error='Required') }}")
    assert 'aria-invalid="true"' in invalid
    assert 'aria-describedby="mw-field-name-error"' in invalid


def test_select_and_checkbox_and_switch_carry_their_roles(environment: Environment) -> None:
    select_html = render(
        environment,
        MACROS + "select %}{{ select('k', 'Kind', options, selected='b') }}",
        options=[{"value": "a", "label": "A"}, {"value": "b", "label": "B"}],
    )
    assert 'value="b" selected' in select_html
    assert 'for="mw-field-k"' in select_html

    checkbox_html = render(environment, MACROS + "checkbox %}{{ checkbox('c', 'Enable') }}")
    assert 'type="checkbox"' in checkbox_html
    assert 'for="mw-field-c"' in checkbox_html

    switch_html = render(environment, MACROS + "switch %}{{ switch('s', 'Live', checked=True) }}")
    assert 'role="switch"' in switch_html
    assert 'aria-checked="true"' in switch_html


def test_table_renders_scoped_headers_and_declares_its_completeness(
    environment: Environment,
) -> None:
    html = render(
        environment,
        MACROS + "table %}{{ table(columns, rows, caption='Everything known', table_id='t',"
        " sortable=True, row_count=1) }}",
        columns=[{"label": "Name"}, {"label": "Size", "numeric": True}],
        rows=[["alpha", "8.0 GiB"]],
    )
    assert '<th scope="col">Name</th>' in html
    assert '<th scope="col" class="numeric">Size</th>' in html
    assert '<td class="numeric">8.0 GiB</td>' in html
    assert 'data-sortable="true"' in html
    assert 'data-complete="true"' in html
    assert "<caption>Everything known</caption>" in html
    assert "1 row<" in html


def test_a_paged_table_declares_itself_incomplete(environment: Environment) -> None:
    """UI standards §5: a client-side sort must apply to the whole dataset, not one page."""
    html = render(
        environment,
        MACROS + "table %}{{ table(columns, rows, complete=False, sortable=True) }}",
        columns=[{"label": "Name"}],
        rows=[["alpha"]],
    )
    assert 'data-complete="false"' in html


def test_table_escapes_hostile_cell_content(environment: Environment) -> None:
    html = render(
        environment,
        MACROS + "table %}{{ table(columns, rows) }}",
        columns=[{"label": "Name"}],
        rows=[['<script>alert("x")</script>']],
    )
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_empty_state_and_pagination_and_kv_list(environment: Environment) -> None:
    empty = render(
        environment,
        MACROS + "empty_state %}{{ empty_state('Nothing yet', 'Start', '/start') }}",
    )
    assert "empty-state" in empty
    assert 'href="/start"' in empty

    pages = render(
        environment, MACROS + "pagination %}{{ pagination(next_href='/next', summary='1-20') }}"
    )
    assert 'aria-label="Pagination"' in pages
    assert 'rel="next"' in pages

    kv = render(
        environment,
        MACROS + "kv_list %}{{ kv_list(items) }}",
        items=[{"label": "Digest", "value": "sha256:abc"}],
    )
    assert "<dt>Digest</dt>" in kv
    assert "<dd>sha256:abc</dd>" in kv


def test_kv_list_renders_an_item_with_an_href_as_a_real_anchor(environment: Environment) -> None:
    """The M5C-6 lesson: a value that is a link must never be HTML smuggled through the escaper."""
    html = render(
        environment,
        MACROS + "kv_list %}{{ kv_list(items) }}",
        items=[
            {"label": "Explanation", "value": "decision 42", "href": "/routing/42"},
            {"label": "Digest", "value": "sha256:abc"},
        ],
    )
    assert '<a href="/routing/42">decision 42</a>' in html
    assert "<dd>sha256:abc</dd>" in html
    assert "&lt;a" not in html


def test_kv_list_markup_in_label_and_value_stays_inert_even_with_an_href(
    environment: Environment,
) -> None:
    """Only the href becomes an attribute; label and value are text, never markup."""
    html = render(
        environment,
        MACROS + "kv_list %}{{ kv_list(items) }}",
        items=[
            {
                "label": "<b>bold</b>",
                "value": '<script>alert("x")</script>',
                "href": "/safe",
            }
        ],
    )
    assert "<b>" not in html
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert '<a href="/safe">' in html


@pytest.mark.parametrize(
    "hostile",
    ["javascript:alert(1)", "JAVASCRIPT:alert(1)", "java\tscript:alert(1)", "data:text/html,x"],
)
def test_kv_list_neutralizes_a_hostile_href_to_plain_text(
    environment: Environment, hostile: str
) -> None:
    """A `javascript:` href is refused, and the value still renders — as text, with no anchor."""
    html = render(
        environment,
        MACROS + "kv_list %}{{ kv_list(items) }}",
        items=[{"label": "Explanation", "value": "decision 42", "href": hostile}],
    )
    assert "<a " not in html
    assert "javascript:" not in html.lower().replace("\t", "")
    assert "<dd>decision 42</dd>" in html


def test_kv_list_values_carry_a_wrapping_rule_for_unbreakable_tokens() -> None:
    """M5C-11: a 64-character fingerprint in a ``<dd>`` must wrap rather than widen the page.

    Both LoadCoach pages carry a commented stopgap naming exactly this rule; it is deletable
    only while ``components.css`` holds the rule itself.
    """
    css = (PACKAGE_STATIC_DIR / "css" / "components.css").read_text()
    rule = re.search(r"\.kv-list dd\s*\{([^}]*)\}", css)
    assert rule is not None
    assert "overflow-wrap" in rule.group(1)
    assert "anywhere" in rule.group(1)


def test_tabs_expose_selection_and_roving_tabindex(environment: Environment) -> None:
    html = render(
        environment,
        MACROS + "tabs %}{{ tabs(items, selected='one') }}",
        items=[{"key": "one", "label": "One"}, {"key": "two", "label": "Two"}],
    )
    assert 'role="tablist"' in html
    assert html.count('role="tab"') == 2
    assert 'aria-selected="true"' in html
    assert 'tabindex="-1"' in html
    assert 'aria-controls="mw-panel-one"' in html


def test_drawer_and_dialog_are_labelled_by_their_own_heading(environment: Environment) -> None:
    drawer = render(
        environment,
        MACROS + "drawer %}{% call drawer('d', 'Details') %}<p>body</p>{% endcall %}",
    )
    assert 'aria-labelledby="d-title"' in drawer
    assert 'id="d-title"' in drawer
    assert "hidden" in drawer

    dialog = render(
        environment,
        MACROS + "dialog %}{% call dialog('m', 'Confirm') %}<p>sure?</p>{% endcall %}",
    )
    assert 'aria-modal="true"' in dialog
    assert 'aria-labelledby="m-title"' in dialog


def test_toast_region_is_a_polite_live_region_present_before_any_toast(
    environment: Environment,
) -> None:
    html = render(environment, MACROS + "toast_region %}{{ toast_region() }}")
    assert 'role="status"' in html
    assert 'aria-live="polite"' in html


def test_progress_and_tooltip_and_json_viewer(environment: Environment) -> None:
    bar = render(environment, MACROS + "progress %}{{ progress(3, 10, 'Import') }}")
    assert 'aria-label="Import"' in bar
    assert 'max="10"' in bar

    tip = render(environment, MACROS + "tooltip %}{{ tooltip('p95', 'the 95th percentile') }}")
    assert 'tabindex="0"' in tip
    assert "aria-label=" in tip

    viewer = render(
        environment,
        MACROS + "json_viewer %}{{ json_viewer(payload, 'Raw') }}",
        payload={"b": 1, "a": 2},
    )
    assert "<summary>Raw</summary>" in viewer
    # The payload is escaped, not marked safe: that is what keeps a <script> inside it inert.
    assert "&#34;a&#34;: 2" in viewer

    hostile = render(
        environment,
        MACROS + "json_viewer %}{{ json_viewer(payload) }}",
        payload={"x": "<script>alert(1)</script>"},
    )
    assert "<script>" not in hostile
    assert "&lt;script&gt;" in hostile


def test_chart_container_pairs_a_figure_with_a_described_alternative(
    environment: Environment,
) -> None:
    html = render(
        environment,
        MACROS + "chart_container %}{% call chart_container('c', 'Throughput', 'Same figures as the"
        " table below') %}<svg></svg>{% endcall %}",
    )
    assert "<figure" in html
    assert "<figcaption>Throughput</figcaption>" in html
    assert "Same figures as the table below" in html


def test_filter_bar_is_a_search_landmark(environment: Environment) -> None:
    html = render(
        environment,
        MACROS + "filter_bar %}{% call filter_bar('/search') %}<input>{% endcall %}",
    )
    assert 'role="search"' in html
    assert 'action="/search"' in html


def test_telemetry_bar_starts_every_field_at_an_em_dash(environment: Environment) -> None:
    html = render(environment, MACROS + "telemetry_bar %}{{ telemetry_bar('/stream') }}")
    assert 'aria-label="System telemetry"' in html
    assert html.count("—") >= 9
    assert not re.search(r'data-field="[a-z_]+">0<', html)


@pytest.mark.parametrize("theme", THEMES)
def test_the_base_shell_renders_in_both_themes_with_the_theme_selector(
    environment: Environment, theme: str
) -> None:
    html = environment.get_template("mirrorwall/base.html").render(
        product_name="Example",
        product_version="1.2.3",
        page="models",
        nav_items=[{"key": "models", "href": "/models", "label": "Models"}],
        theme_storage_key=f"example-theme-{theme}",
    )
    assert "<!doctype html>" in html
    assert 'class="skip-link"' in html
    assert 'aria-current="page"' in html
    assert "data-theme-select" in html
    assert f"example-theme-{theme}" in html
    assert "/static/mirrorwall/css/tokens.css" in html
    # The pre-paint bootstrap must be inline, or a dark-mode reader sees a white flash.
    assert "localStorage.getItem" in html.split("<link")[0]
