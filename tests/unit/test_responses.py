"""The envelopes: one shape, on the success path and the failure path alike."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest
from baseaicore import SuiteError
from starlette.responses import JSONResponse

from mirrorwall.responses import (
    DEFAULT_PAGE_LIMIT,
    MAX_PAGE_LIMIT,
    clamp_limit,
    error_body,
    error_response,
    json_response,
    paginated_response,
)

AT = datetime(2026, 8, 21, 9, 14, 2, 318000, tzinfo=UTC)


class ModelNotFound(SuiteError):
    """A stand-in for an application's own error type."""

    code = "MODEL_NOT_FOUND"


def _body(response: JSONResponse) -> dict[str, Any]:
    decoded: dict[str, Any] = json.loads(bytes(response.body))
    return decoded


def test_the_error_body_matches_the_standards_worked_example_key_for_key() -> None:
    body = error_body(
        code="MODEL_NOT_FOUND",
        message="Model 'qwen3.5:70b' is not available from provider 'ollama'.",
        request_id="01J9K2M4P7Q8R9S0T1U2V3W4X5",
        details={"provider_kind": "ollama", "requested": "qwen3.5:70b", "available_count": 11},
        timestamp=AT,
    )
    assert body == {
        "error": {
            "code": "MODEL_NOT_FOUND",
            "message": "Model 'qwen3.5:70b' is not available from provider 'ollama'.",
            "details": {
                "provider_kind": "ollama",
                "requested": "qwen3.5:70b",
                "available_count": 11,
            },
            "request_id": "01J9K2M4P7Q8R9S0T1U2V3W4X5",
            "timestamp": "2026-08-21T09:14:02.318Z",
        }
    }
    assert list(body["error"]) == ["code", "message", "details", "request_id", "timestamp"]


def test_two_applications_produce_byte_identical_bodies_for_the_same_error() -> None:
    """Acceptance criterion 2, asserted on the bytes rather than on the fields."""
    from mirrorwall.responses import error_body as shared

    first = json.dumps(
        shared(code="NOT_FOUND", message="Gone.", request_id="01J", timestamp=AT),
        separators=(",", ":"),
    )
    second = json.dumps(
        shared(code="NOT_FOUND", message="Gone.", request_id="01J", timestamp=AT),
        separators=(",", ":"),
    )
    assert first == second
    assert first.encode() == second.encode()


def test_a_suite_error_supplies_its_own_code_message_and_details() -> None:
    response = error_response(
        ModelNotFound("Not here.", details={"requested": "x"}),
        status=404,
        request_id="01J",
        timestamp=AT,
    )
    assert response.status_code == 404
    error = _body(response)["error"]
    assert error["code"] == "MODEL_NOT_FOUND"
    assert error["details"] == {"requested": "x"}
    assert response.headers["X-Request-ID"] == "01J"
    assert response.headers["Cache-Control"] == "no-store"


def test_a_plain_mapping_works_too_for_an_error_that_is_not_a_suite_error() -> None:
    response = error_response(
        {"code": "HTTP_ERROR", "message": "Method not allowed."},
        status=405,
        request_id="01J",
        timestamp=AT,
    )
    assert _body(response)["error"]["code"] == "HTTP_ERROR"
    assert _body(response)["error"]["details"] == {}


def test_a_request_id_is_present_on_the_success_path_even_when_the_caller_has_none() -> None:
    """API standards §5 requires it on every response, not most."""
    response = json_response({"ok": True})
    assert response.headers["X-Request-ID"]
    assert response.headers["X-Api-Version"] == "v1"
    assert response.headers["Cache-Control"] == "no-store"


def test_extra_headers_merge_over_the_standard_set() -> None:
    response = json_response({"ok": True}, request_id="01J", headers={"Cache-Control": "private"})
    assert response.headers["Cache-Control"] == "private"
    assert response.headers["X-Request-ID"] == "01J"


@pytest.mark.parametrize(
    ("requested", "expected"),
    [(None, DEFAULT_PAGE_LIMIT), (0, 1), (-5, 1), (20, 20), (10_000, MAX_PAGE_LIMIT)],
)
def test_the_page_limit_is_clamped_into_the_documented_range(
    requested: int | None, expected: int
) -> None:
    assert clamp_limit(requested) == expected


def test_a_page_reports_the_limit_the_server_actually_applied() -> None:
    """A clamped request must be visible to the client, not silently short."""
    response = paginated_response(
        [{"id": 1}], limit=clamp_limit(10_000), next_cursor="abc", has_more=True, request_id="01J"
    )
    body = _body(response)
    assert body["items"] == [{"id": 1}]
    assert body["page"] == {
        "limit": MAX_PAGE_LIMIT,
        "next_cursor": "abc",
        "has_more": True,
        "total": None,
    }


def test_an_uncounted_total_is_null_not_zero() -> None:
    """ "Not counted" and "no rows" are different facts, and a client displays them differently."""
    uncounted = _body(paginated_response([], limit=50))
    counted = _body(paginated_response([], limit=50, total=0))
    assert uncounted["page"]["total"] is None
    assert counted["page"]["total"] == 0
