"""mirrorwall.health — the health payload primitives every application's ``/health`` is built on.

The package supplies the shape and the roll-up rule; each application supplies its own components
(a database, a provider, a queue) and decides what makes each one degraded. That split is the
point: three applications answer "are you healthy?" in the same words, about different things.

``NOT_CONFIGURED`` is a first-class status, not a synonym for ``UNAVAILABLE``. A component nobody
asked for is not broken, and rolling it up as though it were turns every default install into a
red dashboard — the same distinction between "absent" and "bad" that ADR-0016 makes for a
measurement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from baseaicore.timeutil import to_rfc3339, utc_now

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from datetime import datetime

__all__ = ["ComponentHealth", "ComponentStatus", "health_payload", "worst_status"]


class ComponentStatus(StrEnum):
    """One component's verdict.

    Ordered worst-last in :data:`_SEVERITY` rather than by declaration, so adding a status cannot
    silently change how an existing one rolls up.
    """

    OK = "ok"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    NOT_CONFIGURED = "not_configured"


_SEVERITY: dict[ComponentStatus, int] = {
    ComponentStatus.NOT_CONFIGURED: 0,
    ComponentStatus.OK: 1,
    ComponentStatus.DEGRADED: 2,
    ComponentStatus.UNAVAILABLE: 3,
}


@dataclass(frozen=True, slots=True)
class ComponentHealth:
    """One named component's status, with whatever numbers explain it.

    Attributes:
        name: The component, e.g. ``"database"``. Stable across releases: a dashboard keys on it.
        status: The verdict.
        detail: One human-readable sentence. Free of secrets and of paths outside the data root.
        data: Structured figures behind the verdict — free bytes, a latency, a queue depth.
        checked_at: When the check ran. Defaults to now at payload time.
    """

    name: str
    status: ComponentStatus
    detail: str = ""
    data: Mapping[str, Any] = field(default_factory=dict)
    checked_at: datetime | None = None


def worst_status(components: Sequence[ComponentHealth]) -> ComponentStatus:
    """Roll several components up into one overall verdict.

    ``NOT_CONFIGURED`` never worsens the roll-up: a component nobody asked for is not a fault. An
    empty component list is ``OK`` — an application with nothing to check has nothing wrong.

    Args:
        components: The components to roll up.

    Returns:
        The most severe status present, ``OK`` when the only statuses are ``OK`` and
        ``NOT_CONFIGURED``, and ``NOT_CONFIGURED`` only when every component is.
    """
    if not components:
        return ComponentStatus.OK
    statuses = [component.status for component in components]
    if all(status is ComponentStatus.NOT_CONFIGURED for status in statuses):
        return ComponentStatus.NOT_CONFIGURED
    return max(statuses, key=lambda status: _SEVERITY[status])


def health_payload(
    *,
    application: str,
    version: str,
    components: Sequence[ComponentHealth],
    checked_at: datetime | None = None,
) -> dict[str, Any]:
    """Build the ``/health`` body.

    Args:
        application: The application's distribution name, lowercase.
        version: Its version.
        components: Every component it checked.
        checked_at: The instant to record for components that did not carry their own. Injected
            so a test can assert a whole payload without patching the clock.

    Returns:
        The body: overall status, the application's identity, and one entry per component in the
        order given — never reordered, because a dashboard's rows should not move between polls.
    """
    now = checked_at or utc_now()
    return {
        "status": worst_status(components).value,
        "application": application,
        "version": version,
        "checked_at": to_rfc3339(now),
        "components": [
            {
                "name": component.name,
                "status": component.status.value,
                "detail": component.detail,
                "data": dict(component.data),
                "checked_at": to_rfc3339(component.checked_at or now),
            }
            for component in components
        ],
    }
