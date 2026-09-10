"""mirrorwall.middleware — request IDs, Host validation and CSRF, identical in every app.

Two of the three are security controls, and both run **before routing and before any
authentication dependency** (ADR-0026 §1): a rebinding attempt or a forged form post must not
reach a route handler at all, and a middleware is the only layer where that is structurally true
rather than a convention every route is trusted to follow.

They live here rather than in each application for the reason ADR-0026 gives directly: three
implementations of one check is three chances to get it subtly different, and the difference will
be in the application nobody audited.
"""

from __future__ import annotations

import hmac
import logging
import re
import secrets
import time
from typing import TYPE_CHECKING, Any, Final
from urllib.parse import parse_qs

from baseaicore import new_id
from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse

from mirrorwall.responses import error_body

if TYPE_CHECKING:
    from collections.abc import Iterable

    from starlette.types import ASGIApp, Message, Receive, Scope, Send

__all__ = [
    "CSRF_COOKIE_NAME",
    "CSRF_FIELD_NAME",
    "LOOPBACK_HOSTS",
    "REQUEST_ID_PATTERN",
    "CsrfMiddleware",
    "HostValidationMiddleware",
    "RequestIdMiddleware",
    "issue_csrf_token",
    "loopback_allowlist",
    "split_host",
]

logger = logging.getLogger(__name__)

REQUEST_ID_PATTERN: Final = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
"""What a client-supplied ``X-Request-ID`` must match to be echoed rather than replaced.

API standards §5: a ULID or UUID, at most 64 characters, safe charset. A header that fails this —
too long, control characters, a newline that would split the response — is **replaced**, not
sanitized, because a partially cleaned identifier is still an identifier the client chose."""

CSRF_COOKIE_NAME: Final = "__Host-mw-csrf"
"""The double-submit cookie (ADR-0026 §2). The ``__Host-`` prefix is enforced by the browser: it
requires ``Secure``, no ``Domain``, and ``Path=/``, which is what stops a sibling origin or a
subdomain from setting it."""

CSRF_FIELD_NAME: Final = "csrf_token"
"""The hidden form field compared against the cookie with :func:`hmac.compare_digest`."""

LOOPBACK_HOSTS: Final = frozenset({"localhost", "127.0.0.1", "::1", "[::1]", "0.0.0.0"})  # noqa: S104 — the set of bind addresses recognised as loopback-equivalent, not an address to bind

_SAFE_METHODS: Final = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})


def split_host(header: str) -> str:
    """Extract the hostname from a ``Host`` header, handling bracketed IPv6 literals.

    Args:
        header: The raw header value, e.g. ``"localhost:8000"`` or ``"[::1]:8000"``.

    Returns:
        The lowercase hostname with any port removed.
    """
    value = header.strip()
    if value.startswith("["):
        end = value.find("]")
        if end != -1:
            return value[1:end].lower()
    return value.split(":", 1)[0].lower()


def loopback_allowlist(bound_host: str) -> frozenset[str]:
    """Return the ``Host`` values a loopback bind accepts (ADR-0026 §1).

    Args:
        bound_host: The address the server is bound to.

    Returns:
        ``localhost``, ``127.0.0.1``, ``::1`` and the literal bound address.
    """
    return frozenset({"localhost", "127.0.0.1", "::1", bound_host.lower()})


class RequestIdMiddleware:
    """Assign or echo a request ID, bind it to the logging context, and time the response.

    A client-supplied ID is echoed only when it matches :data:`REQUEST_ID_PATTERN`. Anything else
    is replaced with a fresh ULID: a header that a client controls ends up in log lines and in
    response headers, so accepting an arbitrary one is a log-injection and header-splitting
    primitive handed to the caller.
    """

    def __init__(self, app: ASGIApp) -> None:
        """Wrap ``app``."""
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Assign the request ID and add the standard headers to the response."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        supplied = Headers(scope=scope).get("x-request-id")
        request_id = supplied if supplied and REQUEST_ID_PATTERN.match(supplied) else new_id()
        scope.setdefault("state", {})
        scope["state"]["request_id"] = request_id
        started = time.perf_counter()

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(raw=list(message["headers"]))
                headers["X-Request-ID"] = request_id
                headers["X-Api-Version"] = "v1"
                headers["X-Response-Time-Ms"] = f"{(time.perf_counter() - started) * 1000:.1f}"
                if "cache-control" not in headers:
                    headers["Cache-Control"] = "no-store"
                message["headers"] = headers.raw
            await send(message)

        old_factory = logging.getLogRecordFactory()

        def factory(*args: object, **kwargs: object) -> logging.LogRecord:
            record = old_factory(*args, **kwargs)
            record.request_id = request_id
            return record

        logging.setLogRecordFactory(factory)
        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            logging.setLogRecordFactory(old_factory)


class HostValidationMiddleware:
    """Reject a request whose ``Host`` is not on the allowlist, with 421, before routing.

    This is what closes DNS rebinding against an unauthenticated loopback service (ADR-0026 §1): a
    page on an attacker's origin can resolve its own name to ``127.0.0.1`` and reach this server,
    but it cannot change the ``Host`` header the browser sends. Because the check is a middleware,
    it runs before routing and before any authentication dependency, so an unauthenticated
    rebinding attempt never reaches a route at all.
    """

    def __init__(self, app: ASGIApp, *, allowed_hosts: Iterable[str]) -> None:
        """Wrap ``app``, accepting only requests whose ``Host`` is in ``allowed_hosts``."""
        self.app = app
        self._allowed = frozenset(host.lower() for host in allowed_hosts)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Reject a mismatched ``Host`` with 421 before the request reaches routing."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        raw = Headers(scope=scope).get("host", "")
        if split_host(raw) not in self._allowed:
            # `request_id` is deliberately not in `extra`: RequestIdMiddleware's record factory
            # already binds it to every record for this request, and `logging` refuses an `extra`
            # key that would overwrite an existing attribute. Passing it here raises a KeyError
            # from inside the rejection path — the one path that must never fail.
            logger.warning("request.host_rejected", extra={"host": raw})
            await _reject(
                scope,
                receive,
                send,
                status=421,
                code="MISDIRECTED_REQUEST",
                message="The Host header does not match an allowed hostname for this server.",
                details={"host": raw},
            )
            return
        await self.app(scope, receive, send)


def issue_csrf_token() -> str:
    """Mint a CSRF token for a rendered page's form.

    Returns:
        128 bits of URL-safe randomness. The same value goes into the ``__Host-`` cookie and the
        form's hidden field; the middleware compares them with :func:`hmac.compare_digest`.
    """
    return secrets.token_urlsafe(16)


class CsrfMiddleware:
    """Double-submit CSRF protection on HTML form posts (ADR-0026 §2).

    An unsafe request carrying a form content type must present a ``csrf_token`` field equal to
    the ``__Host-`` cookie. Mismatch or absence is 403 ``CSRF_FAILED``.

    **The JSON API is exempt, on stated grounds rather than by omission.** A JSON body cannot be
    produced by a cross-origin HTML form — a form can only send
    ``application/x-www-form-urlencoded``, ``multipart/form-data`` or ``text/plain`` — so a
    request that actually arrives as ``application/json`` has already passed a CORS preflight,
    which fails while CORS is disabled. If CORS is ever enabled the exemption is withdrawn and
    bearer tokens become mandatory; ``json_exempt=False`` is how that is turned off here, so the
    change is one argument rather than a rewrite.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        cookie_name: str = CSRF_COOKIE_NAME,
        field_name: str = CSRF_FIELD_NAME,
        json_exempt: bool = True,
    ) -> None:
        """Wrap ``app``."""
        self.app = app
        self._cookie_name = cookie_name
        self._field_name = field_name
        self._json_exempt = json_exempt

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Reject a form post whose double-submit token is absent or does not match."""
        if scope["type"] != "http" or scope["method"] in _SAFE_METHODS:
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        content_type = headers.get("content-type", "").split(";")[0].strip().lower()
        if content_type == "application/json":
            if self._json_exempt:
                await self.app(scope, receive, send)
                return
            await self._reject(scope, receive, send, "JSON requests require a CSRF token.")
            return
        if content_type not in {"application/x-www-form-urlencoded", "multipart/form-data"}:
            await self.app(scope, receive, send)
            return

        body, receive = await _buffered_body(receive)
        if content_type == "multipart/form-data":
            submitted = _multipart_field(body, headers.get("content-type", ""), self._field_name)
        else:
            submitted = parse_qs(body.decode("utf-8", "replace")).get(self._field_name, [""])[0]
        expected = _cookie(headers.get("cookie", ""), self._cookie_name)
        if not expected or not submitted or not hmac.compare_digest(submitted, expected):
            await self._reject(scope, receive, send, "The form's CSRF token is missing or wrong.")
            return
        await self.app(scope, receive, send)

    async def _reject(self, scope: Scope, receive: Receive, send: Send, message: str) -> None:
        # See the note in HostValidationMiddleware: the record factory already binds request_id.
        logger.warning("request.csrf_failed")
        await _reject(scope, receive, send, status=403, code="CSRF_FAILED", message=message)


async def _reject(  # noqa: PLR0913 — one call site per rejection, every field named
    scope: Scope,
    receive: Receive,
    send: Send,
    *,
    status: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> None:
    """Send the standard error body for a request a middleware refuses to pass on."""
    request_id = scope.get("state", {}).get("request_id") or new_id()
    response = JSONResponse(
        status_code=status,
        content=error_body(code=code, message=message, request_id=request_id, details=details),
        headers={"X-Request-ID": request_id, "Cache-Control": "no-store"},
    )
    await response(scope, receive, send)


def _multipart_field(body: bytes, content_type: str, name: str) -> str:
    """The value of one plain (non-file) field in a ``multipart/form-data`` body, or ``""``.

    Before this, a multipart post was accepted as a form content type and then searched with
    ``parse_qs``, which cannot read a multipart body, so its token was never found and every file
    upload behind this middleware was refused as ``CSRF_FAILED``.

    Deliberately narrow: only the boundary from the header, only a part whose disposition names
    ``name`` with no ``filename``, and the first such part wins. A file part named ``csrf_token``
    cannot stand in for the field.
    """
    boundary = ""
    for parameter in content_type.split(";")[1:]:
        key, _, value = parameter.strip().partition("=")
        if key.lower() == "boundary":
            boundary = value.strip().strip('"')
    if not boundary:
        return ""
    # ponytail: splits the buffered body once; a scan that stops at the field would spare the copy
    # on a very large upload, if the body cap is ever raised past what that costs.
    for part in body.split(b"--" + boundary.encode("latin-1"))[1:]:
        if part.startswith(b"--"):
            break
        head, separator, content = part.lstrip(b"\r\n").partition(b"\r\n\r\n")
        if not separator:
            continue
        disposition = next(
            (
                line
                for line in head.decode("latin-1").split("\r\n")
                if line.lower().startswith("content-disposition:")
            ),
            "",
        )
        parameters: dict[str, str] = {}
        for piece in disposition.split(";")[1:]:
            key, _, raw = piece.strip().partition("=")
            parameters[key.strip().lower()] = raw.strip().strip('"')
        if parameters.get("name") == name and "filename" not in parameters:
            return content.removesuffix(b"\r\n").decode("utf-8", "replace")
    return ""


def _cookie(header: str, name: str) -> str:
    for part in header.split(";"):
        key, _, value = part.strip().partition("=")
        if key == name:
            return value
    return ""


async def _buffered_body(receive: Receive) -> tuple[bytes, Receive]:
    """Read the whole body, and return a ``receive`` that replays it to the application.

    The middleware has to look at the form fields, which consumes the stream; without replaying
    it, every route behind this middleware would see an empty body.
    """
    chunks: list[bytes] = []
    more = True
    while more:
        message = await receive()
        if message["type"] != "http.request":
            break
        chunks.append(message.get("body", b""))
        more = bool(message.get("more_body", False))
    body = b"".join(chunks)
    delivered = False

    async def replay() -> Message:
        nonlocal delivered
        if delivered:
            return {"type": "http.disconnect"}
        delivered = True
        return {"type": "http.request", "body": body, "more_body": False}

    return body, replay
