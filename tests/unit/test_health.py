"""Health primitives: the roll-up rule, and the status that is not a fault."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from mirrorwall.health import ComponentHealth, ComponentStatus, health_payload, worst_status

AT = datetime(2026, 8, 21, 9, 14, 2, 318000, tzinfo=UTC)


def _component(name: str, status: ComponentStatus) -> ComponentHealth:
    return ComponentHealth(name=name, status=status)


def test_the_worst_status_wins() -> None:
    assert (
        worst_status(
            [_component("a", ComponentStatus.OK), _component("b", ComponentStatus.DEGRADED)]
        )
        is ComponentStatus.DEGRADED
    )
    assert (
        worst_status(
            [
                _component("a", ComponentStatus.DEGRADED),
                _component("b", ComponentStatus.UNAVAILABLE),
            ]
        )
        is ComponentStatus.UNAVAILABLE
    )


def test_not_configured_never_worsens_the_roll_up() -> None:
    """A component nobody asked for is not broken; a default install is not a red dashboard."""
    assert (
        worst_status(
            [
                _component("db", ComponentStatus.OK),
                _component("gpu", ComponentStatus.NOT_CONFIGURED),
            ]
        )
        is ComponentStatus.OK
    )


def test_everything_unconfigured_rolls_up_as_unconfigured_not_ok() -> None:
    assert (
        worst_status([_component("a", ComponentStatus.NOT_CONFIGURED)])
        is ComponentStatus.NOT_CONFIGURED
    )


def test_no_components_is_ok() -> None:
    assert worst_status([]) is ComponentStatus.OK


def test_the_payload_keeps_the_order_it_was_given() -> None:
    """A dashboard's rows should not move between polls."""
    components = [
        ComponentHealth(name="database", status=ComponentStatus.OK, detail="1.2 GB"),
        ComponentHealth(
            name="provider",
            status=ComponentStatus.DEGRADED,
            detail="slow",
            data={"latency_ms": 812},
        ),
        ComponentHealth(name="gpu", status=ComponentStatus.NOT_CONFIGURED),
    ]
    payload = health_payload(
        application="example", version="1.0.0", components=components, checked_at=AT
    )
    assert payload["status"] == "degraded"
    assert payload["application"] == "example"
    assert payload["checked_at"] == "2026-08-21T09:14:02.318Z"
    assert [entry["name"] for entry in payload["components"]] == ["database", "provider", "gpu"]
    assert payload["components"][1]["data"] == {"latency_ms": 812}
    assert payload["components"][2]["status"] == "not_configured"


def test_a_component_may_carry_its_own_check_time() -> None:
    earlier = datetime(2026, 8, 21, 9, 0, 0, tzinfo=UTC)
    payload = health_payload(
        application="example",
        version="1.0.0",
        components=[
            ComponentHealth(name="cached", status=ComponentStatus.OK, checked_at=earlier),
            ComponentHealth(name="live", status=ComponentStatus.OK),
        ],
        checked_at=AT,
    )
    assert payload["components"][0]["checked_at"] == "2026-08-21T09:00:00.000Z"
    assert payload["components"][1]["checked_at"] == "2026-08-21T09:14:02.318Z"


@pytest.mark.parametrize("status", list(ComponentStatus))
def test_every_status_serializes_as_its_wire_string(status: ComponentStatus) -> None:
    payload = health_payload(
        application="example",
        version="1.0.0",
        components=[_component("x", status)],
        checked_at=AT,
    )
    assert payload["components"][0]["status"] == status.value
    assert isinstance(payload["components"][0]["status"], str)
