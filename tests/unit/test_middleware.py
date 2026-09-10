"""Request IDs, Host validation and CSRF — the two security controls tested at the ASGI edge.

They are exercised through a real Starlette app with a route that records whether it ran, because
"the check runs before routing" is the property that matters and it is not observable from a unit
call into the middleware object.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from mirrorwall.middleware import (
    CSRF_COOKIE_NAME,
    CSRF_FIELD_NAME,
    REQUEST_ID_PATTERN,
    CsrfMiddleware,
    HostValidationMiddleware,
    RequestIdMiddleware,
    issue_csrf_token,
    loopback_allowlist,
    split_host,
)

if TYPE_CHECKING:
    from starlette.requests import Request

REACHED: list[str] = []


async def _handler(request: Request) -> PlainTextResponse:
    REACHED.append(request.url.path)
    body = await request.body()
    return PlainTextResponse(body.decode() or "ok")


@pytest.fixture(autouse=True)
def _reset() -> None:
    REACHED.clear()


def _app(*, allowed_hosts: tuple[str, ...] = ("testserver",), csrf: bool = False) -> Starlette:
    app = Starlette(
        routes=[Route("/x", _handler, methods=["GET", "POST"])],
    )
    if csrf:
        app.add_middleware(CsrfMiddleware)
    app.add_middleware(HostValidationMiddleware, allowed_hosts=allowed_hosts)
    app.add_middleware(RequestIdMiddleware)
    return app


# --- request IDs ---------------------------------------------------------------------------


def test_a_valid_client_supplied_request_id_is_echoed() -> None:
    with TestClient(_app()) as client:
        response = client.get("/x", headers={"X-Request-ID": "01J9K2M4P7Q8R9S0T1U2V3W4X5"})
    assert response.headers["X-Request-ID"] == "01J9K2M4P7Q8R9S0T1U2V3W4X5"


@pytest.mark.parametrize(
    "hostile",
    [
        "a" * 65,
        "has spaces",
        "has\nnewline",
        "has\r\nSet-Cookie: x=1",
        "semi;colon",
        "",
        "\x00null",
    ],
)
def test_a_hostile_request_id_is_replaced_not_sanitized(hostile: str) -> None:
    """A header the client controls reaches log lines and response headers."""
    with TestClient(_app()) as client:
        response = client.get("/x", headers={"X-Request-ID": hostile})
    returned = response.headers["X-Request-ID"]
    assert returned != hostile
    assert REQUEST_ID_PATTERN.match(returned)


def test_a_request_with_no_id_gets_one_and_the_response_is_timed() -> None:
    with TestClient(_app()) as client:
        response = client.get("/x")
    assert REQUEST_ID_PATTERN.match(response.headers["X-Request-ID"])
    assert response.headers["X-Api-Version"] == "v1"
    assert float(response.headers["X-Response-Time-Ms"]) >= 0
    assert response.headers["Cache-Control"] == "no-store"


def test_the_request_id_is_bound_to_every_log_record_for_the_request(
    caplog: pytest.LogCaptureFixture,
) -> None:
    import logging

    async def logging_handler(request: Request) -> PlainTextResponse:
        logging.getLogger("example").warning("something happened")
        return PlainTextResponse("ok")

    app = Starlette(routes=[Route("/log", logging_handler)])
    app.add_middleware(RequestIdMiddleware)
    with caplog.at_level(logging.WARNING), TestClient(app) as client:
        response = client.get("/log", headers={"X-Request-ID": "01JBOUND"})
    assert response.status_code == 200
    bound = [record for record in caplog.records if record.name == "example"]
    assert bound
    assert all(getattr(record, "request_id", None) == "01JBOUND" for record in bound)


# --- Host validation ----------------------------------------------------------------------


def test_an_allowed_host_passes_and_a_disallowed_one_is_421_before_routing() -> None:
    with TestClient(_app(allowed_hosts=("testserver",))) as client:
        assert client.get("/x").status_code == 200
        assert REACHED == ["/x"]
        REACHED.clear()
        rejected = client.get("/x", headers={"Host": "evil.example.com"})
    assert rejected.status_code == 421
    assert rejected.json()["error"]["code"] == "MISDIRECTED_REQUEST"
    assert rejected.json()["error"]["details"]["host"] == "evil.example.com"
    assert REACHED == [], "the request reached the route despite a rejected Host"


def test_the_check_runs_before_any_authentication_dependency() -> None:
    """ADR-0026 §1: an unauthenticated rebinding attempt never reaches a route.

    A route that would raise if reached stands in for an auth dependency: reaching it at all is
    the failure, whatever it would then have done.
    """

    async def never(request: Request) -> PlainTextResponse:  # pragma: no cover — must not run
        message = "authentication ran before the Host check"
        raise AssertionError(message)

    app = Starlette(routes=[Route("/private", never)])
    app.add_middleware(HostValidationMiddleware, allowed_hosts=("localhost",))
    app.add_middleware(RequestIdMiddleware)
    with TestClient(app, base_url="http://evil.example.com") as client:
        assert client.get("/private").status_code == 421


def test_a_port_and_an_ipv6_literal_are_handled() -> None:
    assert split_host("localhost:8000") == "localhost"
    assert split_host("[::1]:8000") == "::1"
    assert split_host("  LOCALHOST  ") == "localhost"
    assert loopback_allowlist("127.0.0.1") == {"localhost", "127.0.0.1", "::1"}
    assert "192.168.1.5" in loopback_allowlist("192.168.1.5")


# --- CSRF ---------------------------------------------------------------------------------


def test_a_forged_form_post_is_rejected() -> None:
    with TestClient(_app(csrf=True)) as client:
        response = client.post("/x", data={CSRF_FIELD_NAME: "guessed"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CSRF_FAILED"
    assert REACHED == []


def test_a_form_post_with_no_token_at_all_is_rejected() -> None:
    with TestClient(_app(csrf=True)) as client:
        response = client.post("/x", data={"field": "value"})
    assert response.status_code == 403
    assert REACHED == []


def test_a_valid_double_submit_succeeds_and_the_body_still_reaches_the_route() -> None:
    """The middleware reads the body to check the token; the route must still see it."""
    token = issue_csrf_token()
    with TestClient(_app(csrf=True)) as client:
        client.cookies.set(CSRF_COOKIE_NAME, token)
        response = client.post("/x", data={CSRF_FIELD_NAME: token, "note": "hello"})
    assert response.status_code == 200
    assert "note=hello" in response.text
    assert REACHED == ["/x"]


def test_a_multipart_form_with_a_valid_token_succeeds_and_the_body_still_reaches_the_route() -> (
    None
):
    """A file upload is a form post too. Its token used to be searched for with ``parse_qs``,
    which cannot read a multipart body, so every upload was refused as ``CSRF_FAILED``."""
    token = issue_csrf_token()
    with TestClient(_app(csrf=True)) as client:
        client.cookies.set(CSRF_COOKIE_NAME, token)
        response = client.post(
            "/x",
            data={CSRF_FIELD_NAME: token},
            files={"file": ("notes.md", b"# hello", "text/markdown")},
        )
    assert response.status_code == 200
    assert "# hello" in response.text
    assert REACHED == ["/x"]


def test_a_multipart_form_with_a_wrong_or_missing_token_is_rejected() -> None:
    token = issue_csrf_token()
    with TestClient(_app(csrf=True)) as client:
        client.cookies.set(CSRF_COOKIE_NAME, token)
        wrong = client.post(
            "/x", data={CSRF_FIELD_NAME: "guessed"}, files={"file": ("a.md", b"a", "text/plain")}
        )
        missing = client.post("/x", files={"file": ("a.md", b"a", "text/plain")})
    assert (wrong.status_code, missing.status_code) == (403, 403)
    assert REACHED == []


def test_a_file_part_named_like_the_token_cannot_stand_in_for_the_field() -> None:
    """Only a plain field counts: an uploaded *file* named ``csrf_token`` is not the token."""
    token = issue_csrf_token()
    with TestClient(_app(csrf=True)) as client:
        client.cookies.set(CSRF_COOKIE_NAME, token)
        response = client.post(
            "/x", files={CSRF_FIELD_NAME: ("csrf_token", token.encode(), "text/plain")}
        )
    assert response.status_code == 403
    assert REACHED == []


def test_a_json_post_is_exempt_while_cors_is_disabled_and_can_be_switched_off() -> None:
    """ADR-0026 §2: exempt on stated grounds, and the grounds are one argument to withdraw."""
    with TestClient(_app(csrf=True)) as client:
        assert client.post("/x", json={"a": 1}).status_code == 200

    strict = Starlette(routes=[Route("/x", _handler, methods=["POST"])])
    strict.add_middleware(CsrfMiddleware, json_exempt=False)
    strict.add_middleware(RequestIdMiddleware)
    REACHED.clear()
    with TestClient(strict) as client:
        response = client.post("/x", json={"a": 1})
    assert response.status_code == 403
    assert REACHED == []


def test_safe_methods_and_unknown_content_types_are_not_checked() -> None:
    with TestClient(_app(csrf=True)) as client:
        assert client.get("/x").status_code == 200
        assert (
            client.post("/x", content=b"raw", headers={"Content-Type": "text/plain"}).status_code
            == 200
        )


def test_two_issued_tokens_differ() -> None:
    assert issue_csrf_token() != issue_csrf_token()
    assert len(issue_csrf_token()) >= 20
