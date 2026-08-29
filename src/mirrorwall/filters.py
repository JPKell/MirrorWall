"""mirrorwall.filters — the template filters every application in the suite renders through.

One rule shapes most of this module. An absent measurement is an em dash, never a zero
(:doc:`ADR-0016 <../../adr/0016-unsupported-vs-zero>`, UI/UX standards §3): a machine that could
not read its GPU temperature did not read it as zero degrees, and a zero is indistinguishable
from a real reading the moment it reaches an average or a chart.

:func:`measurement` is the **only** sanctioned way a template touches a
:class:`~baseaicore.Measurement` (spec §2). ``UNSUPPORTED`` refuses ``__bool__``, so
``{% if value %}`` on a measurement raises rather than rendering blank — correct behaviour, and
worth knowing before it happens. Templates write ``{{ value | measurement }}`` and
``{% if value is supported %}``.
"""

from __future__ import annotations

import json
import posixpath
from datetime import datetime, timedelta
from typing import Any, Final

from baseaicore import UNSUPPORTED, is_supported
from baseaicore.timeutil import to_rfc3339
from markupsafe import Markup, escape

__all__ = [
    "EM_DASH",
    "STATIC_URL_PREFIX",
    "asset_url",
    "bytes_human",
    "duration_human",
    "is_supported_test",
    "json_pretty",
    "measurement",
    "register_filters",
    "timestamp",
    "truncate_middle",
]

EM_DASH: Final = "—"
"""What an absent value renders as, everywhere in the suite. Never ``0``, never blank."""

STATIC_URL_PREFIX: Final = "/static/mirrorwall"
"""Where :func:`mount_static` serves this package's own assets from."""

_BYTE_UNITS: Final = ("KiB", "MiB", "GiB", "TiB", "PiB")


def bytes_human(value: object) -> str:
    """Render a byte count at human scale.

    Args:
        value: A byte count, ``None``, or ``UNSUPPORTED``.

    Returns:
        The scaled string, or an em dash for an absent value — never ``"0 B"``, which is a real
        measurement of an empty thing and must stay distinguishable from an unmeasured one.
    """
    if value is None or not is_supported(value) or not isinstance(value, (int, float)):
        return EM_DASH
    if value < 1024:
        return f"{int(value)} B"
    scaled = float(value)
    for unit in _BYTE_UNITS:
        scaled /= 1024
        if scaled < 1024 or unit == _BYTE_UNITS[-1]:
            return f"{scaled:.1f} {unit}"
    raise AssertionError("unreachable: the final unit always returns")  # pragma: no cover


def duration_human(value: object) -> str:
    """Render a duration in seconds at human scale.

    Args:
        value: Seconds as a number, a :class:`~datetime.timedelta`, ``None``, or ``UNSUPPORTED``.

    Returns:
        ``"820 ms"``, ``"1.4 s"``, ``"2m 05s"`` or ``"3h 12m"``; an em dash for an absent value.
    """
    if isinstance(value, timedelta):
        value = value.total_seconds()
    if value is None or not is_supported(value) or not isinstance(value, (int, float)):
        return EM_DASH
    seconds = float(value)
    if seconds < 1:
        return f"{seconds * 1000:.0f} ms"
    if seconds < 60:
        return f"{seconds:.1f} s"
    if seconds < 3600:
        return f"{int(seconds // 60)}m {int(seconds % 60):02d}s"
    return f"{int(seconds // 3600)}h {int(seconds % 3600 // 60):02d}m"


def timestamp(value: object) -> str:
    """Render an instant as RFC 3339 in UTC.

    Args:
        value: A timezone-aware :class:`~datetime.datetime`, ``None``, or ``UNSUPPORTED``.

    Returns:
        The RFC 3339 string, or an em dash.
    """
    if not isinstance(value, datetime):
        return EM_DASH
    return to_rfc3339(value)


def measurement(value: object, reason: str | None = None, unit: str | None = None) -> Markup:
    """Render a measurement, or an em dash carrying why it is absent.

    The only sanctioned way a template touches a :class:`~baseaicore.Measurement`. An
    ``UNSUPPORTED`` value renders as an em dash with the producer's own reason in a ``title``
    attribute and in ``aria-label``, so the absence is visible to a reader and to a screen reader
    alike, and is never a zero.

    Args:
        value: The measurement.
        reason: Why it is unavailable, from the producer (SweatMeter's ``unavailable_reasons``,
            a run's ``unsupported_reason`` column). Rendered as a tooltip.
        unit: A unit suffix appended to a present value, e.g. ``"W"``.

    Returns:
        Escaped markup: an ``<span>`` for an absent value, the escaped number otherwise.
    """
    if value is None or value is UNSUPPORTED or not is_supported(value):
        explanation = reason or "not measurable in this environment"
        return Markup(
            '<span class="muted" title="{reason}" aria-label="Unavailable: {reason}">{dash}</span>'
        ).format(reason=explanation, dash=EM_DASH)
    rendered = f"{value:g}" if isinstance(value, float) else str(value)
    if unit:
        return Markup("{value} <span class='unit'>{unit}</span>").format(value=rendered, unit=unit)
    return escape(rendered)


def is_supported_test(value: object) -> bool:
    """Jinja test: whether a measurement carries a real reading.

    Registered as ``supported`` so a template writes ``{% if value is supported %}``. It exists
    because ``{% if value %}`` on an ``UNSUPPORTED`` raises — deliberately (ADR-0016) — and a
    template needs a way to ask the question that does not.

    Args:
        value: The measurement.

    Returns:
        Whether it can be rendered as a number.
    """
    return value is not None and is_supported(value)


def truncate_middle(value: object, length: int = 40, ellipsis: str = "…") -> str:
    """Shorten a long identifier from the middle, keeping both ends readable.

    A canonical model ID is distinguished by its tail as much as its head, so an ordinary
    right-truncation removes the half that disambiguates it.

    Args:
        value: The string to shorten.
        length: The maximum rendered length, including the ellipsis.
        ellipsis: What replaces the removed middle.

    Returns:
        The original string when it already fits, otherwise head + ellipsis + tail.

    Raises:
        ValueError: ``length`` is too small to hold the ellipsis and one character either side.
    """
    text = "" if value is None else str(value)
    minimum = len(ellipsis) + 2
    if length < minimum:
        message = (
            f"length must be at least {minimum} to hold {ellipsis!r} and one character either side"
        )
        raise ValueError(message)
    if len(text) <= length:
        return text
    room = length - len(ellipsis)
    head = room - room // 2
    return f"{text[:head]}{ellipsis}{text[len(text) - room // 2 :]}"


def json_pretty(value: object, indent: int = 2) -> str:
    """Render a value as indented JSON for a ``<pre>`` block.

    Args:
        value: Anything JSON-serializable. Anything else is rendered with ``str`` rather than
            raising, because a viewer that crashes the page it is diagnosing is useless.
        indent: Indentation width.

    Returns:
        The JSON text. Not marked safe: the caller's autoescaping still applies, which is what
        keeps a ``<script>`` inside a payload inert.
    """
    try:
        return json.dumps(value, indent=indent, sort_keys=True, default=str)
    except (TypeError, ValueError):  # pragma: no cover — default=str covers all practical inputs
        return str(value)


def asset_url(path: str, *, prefix: str = STATIC_URL_PREFIX) -> str:
    """Return the URL this package's asset is served from.

    Phase 1 emits a plain, traversal-safe path. Phase 2's :mod:`mirrorwall.static` replaces the
    implementation with the content-hashed form; the template seam is this function's name and
    signature, so that change is invisible to every consumer's templates.

    Args:
        path: A path relative to ``mirrorwall/static/``, e.g. ``"css/tokens.css"``.
        prefix: The URL the static mount serves from.

    Returns:
        The absolute URL path.

    Raises:
        ValueError: ``path`` is absolute or escapes the static root — a template must not be able
            to address anything outside the package's own assets.
    """
    cleaned = path.strip()
    if cleaned.startswith("/") or "\\" in cleaned:
        message = f"asset path must be relative to the static root: {path!r}"
        raise ValueError(message)
    normalized = posixpath.normpath(cleaned)
    if normalized.startswith("..") or normalized == ".":
        message = f"asset path escapes the static root: {path!r}"
        raise ValueError(message)
    return f"{prefix}/{normalized}"


def register_filters(filters: dict[str, Any], tests: dict[str, Any]) -> None:
    """Install every shared filter and test onto a Jinja environment's registries.

    Args:
        filters: The environment's ``filters`` mapping.
        tests: The environment's ``tests`` mapping.
    """
    filters.update(
        {
            "bytes_human": bytes_human,
            "duration_human": duration_human,
            "timestamp": timestamp,
            "measurement": measurement,
            "truncate_middle": truncate_middle,
            "json_pretty": json_pretty,
            "asset_url": asset_url,
        }
    )
    tests["supported"] = is_supported_test
