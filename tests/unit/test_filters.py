"""The shared filters, and the one rule they all serve: absent is an em dash, never a zero."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from baseaicore import UNSUPPORTED

from mirrorwall.filters import (
    EM_DASH,
    asset_url,
    bytes_human,
    duration_human,
    is_supported_test,
    json_pretty,
    measurement,
    safe_href,
    timestamp,
    truncate_middle,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [(0, "0 B"), (512, "512 B"), (1024, "1.0 KiB"), (8 * 1024**3, "8.0 GiB")],
)
def test_bytes_human_scales(value: int, expected: str) -> None:
    assert bytes_human(value) == expected


@pytest.mark.parametrize("value", [None, UNSUPPORTED, "not a number"])
def test_bytes_human_renders_an_em_dash_for_an_absent_value(value: object) -> None:
    assert bytes_human(value) == EM_DASH


def test_zero_bytes_is_a_measurement_and_stays_distinguishable_from_an_absence() -> None:
    """A file of zero bytes was measured; an unreported size was not (ADR-0016)."""
    assert bytes_human(0) != bytes_human(UNSUPPORTED)


@pytest.mark.parametrize(
    ("value", "expected"),
    [(0.82, "820 ms"), (1.44, "1.4 s"), (125, "2m 05s"), (11520, "3h 12m")],
)
def test_duration_human_scales(value: float, expected: str) -> None:
    assert duration_human(value) == expected


def test_duration_human_accepts_a_timedelta_and_refuses_an_absence() -> None:
    assert duration_human(timedelta(seconds=125)) == "2m 05s"
    assert duration_human(UNSUPPORTED) == EM_DASH


def test_timestamp_renders_rfc3339_and_an_em_dash_otherwise() -> None:
    assert timestamp(datetime(2026, 8, 29, 12, 0, tzinfo=UTC)) == "2026-08-29T12:00:00.000Z"
    assert timestamp(None) == EM_DASH
    assert timestamp(UNSUPPORTED) == EM_DASH


def test_measurement_renders_an_em_dash_with_the_reason_and_never_zero() -> None:
    rendered = str(measurement(UNSUPPORTED, "no GPU detected"))
    assert EM_DASH in rendered
    assert "no GPU detected" in rendered
    assert 'title="no GPU detected"' in rendered
    assert 'aria-label="Unavailable: no GPU detected"' in rendered
    assert "0" not in rendered


def test_measurement_without_a_reason_still_explains_itself() -> None:
    rendered = str(measurement(UNSUPPORTED))
    assert "not measurable in this environment" in rendered


def test_measurement_renders_a_present_value_with_its_unit() -> None:
    assert str(measurement(42)) == "42"
    assert str(measurement(41.5)) == "41.5"
    assert "W" in str(measurement(120, unit="W"))


def test_measurement_escapes_a_hostile_reason() -> None:
    rendered = str(measurement(UNSUPPORTED, '<script>alert("x")</script>'))
    assert "<script>" not in rendered
    assert "&lt;script&gt;" in rendered


def test_supported_test_answers_the_question_truthiness_refuses_to() -> None:
    with pytest.raises(TypeError):
        bool(UNSUPPORTED)
    assert is_supported_test(UNSUPPORTED) is False
    assert is_supported_test(None) is False
    assert is_supported_test(0) is True


def test_truncate_middle_keeps_both_ends() -> None:
    canonical = "ollama/qwen3.5:9b-q8_0@sha256:1f3a9c4e2b70"
    shortened = truncate_middle(canonical, 24)
    assert len(shortened) == 24
    assert shortened.startswith("ollama/")
    assert shortened.endswith("2b70")
    assert "…" in shortened


def test_truncate_middle_leaves_a_short_string_alone_and_refuses_a_useless_length() -> None:
    assert truncate_middle("short", 40) == "short"
    with pytest.raises(ValueError, match="length must be at least"):
        truncate_middle("anything", 2)


def test_json_pretty_is_sorted_stable_and_survives_an_unserializable_value() -> None:
    assert json_pretty({"b": 1, "a": 2}) == '{\n  "a": 2,\n  "b": 1\n}'
    # An unserializable value falls back to str() rather than raising: a viewer that crashes the
    # page it is diagnosing is useless.
    assert json_pretty({"x": UNSUPPORTED}).strip().startswith("{")


def test_asset_url_joins_under_the_static_prefix() -> None:
    assert asset_url("css/tokens.css") == "/static/mirrorwall/css/tokens.css"
    assert asset_url("./js/theme.js") == "/static/mirrorwall/js/theme.js"


@pytest.mark.parametrize(
    "path", ["/etc/passwd", "../../../etc/passwd", "css/../../secrets", "css\\tokens.css"]
)
def test_asset_url_refuses_to_address_anything_outside_the_static_root(path: str) -> None:
    with pytest.raises(ValueError, match="static root"):
        asset_url(path)


@pytest.mark.parametrize(
    "value",
    [
        "/jobs/42",
        "#section",
        "?page=2",
        "../up/one",
        "https://example.test/models",
        "http://127.0.0.1:8792/",
        "mailto:someone@example.test",
    ],
)
def test_safe_href_passes_relative_urls_and_the_allowlisted_schemes(value: str) -> None:
    assert safe_href(value) == value


@pytest.mark.parametrize(
    "value",
    [
        "javascript:alert(1)",
        "JAVASCRIPT:alert(1)",
        "JaVaScRiPt:alert(1)",
        "data:text/html,<script>alert(1)</script>",
        "vbscript:msgbox(1)",
        "file:///etc/passwd",
    ],
)
def test_safe_href_refuses_every_scheme_off_the_allowlist(value: str) -> None:
    """The escaper cannot help: `javascript:` is well-formed attribute text — refuse, not escape."""
    assert safe_href(value) is None


def test_safe_href_strips_the_characters_browsers_strip_before_deciding() -> None:
    """`java\\tscript:` parses scheme-less here but as `javascript:` in a browser — clean first."""
    assert safe_href("java\tscript:alert(1)") is None
    assert safe_href("java\nscript:alert(1)") is None
    assert safe_href("\t/jobs/42\n") == "/jobs/42"


def test_safe_href_refuses_a_non_string_and_an_empty_string() -> None:
    assert safe_href(None) is None
    assert safe_href(42) is None
    assert safe_href("") is None
    assert safe_href("   ") is None


def test_safe_href_does_not_mistake_a_path_colon_for_a_scheme() -> None:
    """RFC 3986: a scheme is `[a-zA-Z][a-zA-Z0-9+.-]*` — `/a/b:c` has none."""
    assert safe_href("/models/ollama/qwen@sha256:abc") == "/models/ollama/qwen@sha256:abc"
