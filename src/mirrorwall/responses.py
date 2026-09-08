"""mirrorwall.responses — the JSON, error and pagination envelopes every application emits.

One shape, everywhere. API standards §4 is explicit that an error is **not** wrapped in a SetSpec
envelope: an error describes one request, not a document that outlives it (ADR-0025 §4). The
success and pagination shapes follow the same rule for the same reason — a list of rows a client
is about to render is not an artifact anyone will diff six months later.

What this module guarantees, and what its tests assert, is that every application produces
**byte-compatible** bodies: the same key order, the same timestamp format, the same
``request_id`` on success and on failure alike.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from baseaicore import SuiteError, new_id
from baseaicore.timeutil import to_rfc3339, utc_now
from starlette.responses import JSONResponse

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from datetime import datetime

__all__ = [
    "DEFAULT_PAGE_LIMIT",
    "MAX_PAGE_LIMIT",
    "clamp_limit",
    "error_body",
    "error_response",
    "json_response",
    "paginated_response",
]

DEFAULT_PAGE_LIMIT: Final = 50
"""API standards §6's default page size."""

MAX_PAGE_LIMIT: Final = 500
"""API standards §6's ceiling. An over-limit request is clamped, and the response says so in
``page.limit`` rather than silently returning fewer rows than asked for."""


def _headers(request_id: str) -> dict[str, str]:
    return {"X-Request-ID": request_id, "X-Api-Version": "v1", "Cache-Control": "no-store"}


def json_response(
    payload: Any,
    *,
    status: int = 200,
    request_id: str | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    """Return a success response carrying ``payload`` and this request's ID.

    Args:
        payload: The body. Serialized as-is; a pydantic model is dumped by the caller, so this
            function never has to guess between ``mode="json"`` and ``mode="python"``.
        status: The HTTP status. Defaults to 200.
        request_id: This request's ID. Generated when the caller has none, so a response is never
            emitted without one — API standards §5 requires it on every response, not most.
        headers: Extra headers, merged over the standard set.

    Returns:
        The response, with ``X-Request-ID``, ``X-Api-Version`` and ``Cache-Control: no-store``.
    """
    resolved = request_id or new_id()
    merged = _headers(resolved) | dict(headers or {})
    return JSONResponse(status_code=status, content=payload, headers=merged)


def error_body(
    *,
    code: str,
    message: str,
    request_id: str,
    details: Mapping[str, Any] | None = None,
    timestamp: datetime | None = None,
) -> dict[str, Any]:
    """Build the error body every application in the suite emits (API standards §4).

    Args:
        code: ``SCREAMING_SNAKE_CASE``, stable, documented in the component's spec. Clients branch
            on this, never on ``message``.
        message: One human-readable sentence, safe to display.
        request_id: This request's ID; it also appears in every log line for the request.
        details: Structured and machine-usable. Never credentials, never prompt content.
        timestamp: When the error was produced. Defaults to now.

    Returns:
        ``{"error": {...}}`` with the keys in the order the standard prints them, so two
        applications' bodies are byte-identical for the same error.
    """
    return {
        "error": {
            "code": code,
            "message": message,
            "details": dict(details or {}),
            "request_id": request_id,
            "timestamp": to_rfc3339(timestamp or utc_now()),
        }
    }


def error_response(
    error: SuiteError | Mapping[str, Any],
    *,
    status: int,
    request_id: str,
    timestamp: datetime | None = None,
) -> JSONResponse:
    """Return the standard error response for a :class:`~baseaicore.SuiteError` or a plain body.

    Args:
        error: The failure. A :class:`~baseaicore.SuiteError` supplies its own ``code``,
            ``message`` and ``details``; a mapping supplies them under those keys.
        status: The HTTP status, chosen by the application from API standards §4's table — this
            package deliberately holds no code-to-status map, because the codes are the
            applications' own.
        request_id: This request's ID.
        timestamp: When the error was produced. Defaults to now.

    Returns:
        The response, with the standard headers.
    """
    details: Mapping[str, Any] | None
    if isinstance(error, SuiteError):
        code, message, details = error.code, error.message, error.details
    else:
        code, message, details = str(error["code"]), str(error["message"]), error.get("details")
    body = error_body(
        code=code, message=message, request_id=request_id, details=details, timestamp=timestamp
    )
    return JSONResponse(status_code=status, content=body, headers=_headers(request_id))


def clamp_limit(limit: int | None, *, maximum: int = MAX_PAGE_LIMIT) -> int:
    """Clamp a requested page size into the documented range (API standards §6).

    Args:
        limit: What the caller asked for, or ``None`` for the default.
        maximum: The ceiling.

    Returns:
        The effective limit, at least 1 and at most ``maximum``. The response reports this value
        in ``page.limit``, so a clamped request is visible to the client rather than silently
        returning fewer rows than it asked for.
    """
    if limit is None:
        return min(DEFAULT_PAGE_LIMIT, maximum)
    return max(1, min(limit, maximum))


def paginated_response(
    items: Sequence[Any],
    *,
    limit: int,
    next_cursor: str | None = None,
    has_more: bool = False,
    total: int | None = None,
    request_id: str | None = None,
) -> JSONResponse:
    """Return one page of a cursor-paginated collection (API standards §6).

    Args:
        items: This page's rows, already serialized.
        limit: The **effective** limit, after clamping — what the server actually applied.
        next_cursor: The opaque cursor for the following page, or ``None`` at the end.
        has_more: Whether a following page exists.
        total: The total row count, when it is cheap to know. ``None`` means "not counted", which
            is a different statement from ``0`` and is transported as ``null`` rather than a zero
            a client might display.
        request_id: This request's ID.

    Returns:
        ``{"items": [...], "page": {...}}`` with the standard headers.
    """
    return json_response(
        {
            "items": list(items),
            "page": {
                "limit": limit,
                "next_cursor": next_cursor,
                "has_more": has_more,
                "total": total,
            },
        },
        request_id=request_id,
    )
