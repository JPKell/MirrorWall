"""MirrorWall — the shared UI and web-edge toolkit for the suite's four applications.

Design tokens, a layout shell, component macros, template filters, JSON and error envelopes, SSE
plumbing, request-ID, Host-validation and CSRF middleware, static mounting and health
primitives — so FreeWeight, LoadCoach, IdeaPress and PromptCadence look and behave like one product
family without sharing a single page.

It knows nothing about benchmarks, routing or content, and a term-scan test enforces that: no
application vocabulary appears anywhere in this package, in Python, in a template, in a CSS class
name or in a JS module name.
"""

from __future__ import annotations

from mirrorwall.__about__ import __version__
from mirrorwall.filters import (
    EM_DASH,
    STATIC_URL_PREFIX,
    asset_url,
    bytes_human,
    duration_human,
    is_supported_test,
    json_pretty,
    measurement,
    register_filters,
    safe_href,
    timestamp,
    truncate_middle,
)
from mirrorwall.health import (
    ComponentHealth,
    ComponentStatus,
    health_payload,
    worst_status,
)
from mirrorwall.middleware import (
    CSRF_COOKIE_NAME,
    CSRF_FIELD_NAME,
    CsrfMiddleware,
    HostValidationMiddleware,
    RequestIdMiddleware,
    issue_csrf_token,
    loopback_allowlist,
)
from mirrorwall.responses import (
    DEFAULT_PAGE_LIMIT,
    MAX_PAGE_LIMIT,
    clamp_limit,
    error_body,
    error_response,
    json_response,
    paginated_response,
)
from mirrorwall.sse import (
    TOKEN_EVENT,
    Event,
    EventBroker,
    EventSource,
    Subscription,
    format_frame,
    parse_last_event_id,
    sse_response,
)
from mirrorwall.static import HashedStaticFiles, mount_static
from mirrorwall.templating import (
    DEFAULT_THEME_STORAGE_KEY,
    PACKAGE_STATIC_DIR,
    PACKAGE_TEMPLATE_DIR,
    create_template_environment,
)

__all__ = [
    "CSRF_COOKIE_NAME",
    "CSRF_FIELD_NAME",
    "DEFAULT_PAGE_LIMIT",
    "DEFAULT_THEME_STORAGE_KEY",
    "EM_DASH",
    "MAX_PAGE_LIMIT",
    "PACKAGE_STATIC_DIR",
    "PACKAGE_TEMPLATE_DIR",
    "STATIC_URL_PREFIX",
    "TOKEN_EVENT",
    "ComponentHealth",
    "ComponentStatus",
    "CsrfMiddleware",
    "Event",
    "EventBroker",
    "EventSource",
    "HashedStaticFiles",
    "HostValidationMiddleware",
    "RequestIdMiddleware",
    "Subscription",
    "__version__",
    "asset_url",
    "bytes_human",
    "clamp_limit",
    "create_template_environment",
    "duration_human",
    "error_body",
    "error_response",
    "format_frame",
    "health_payload",
    "is_supported_test",
    "issue_csrf_token",
    "json_pretty",
    "json_response",
    "loopback_allowlist",
    "measurement",
    "mount_static",
    "paginated_response",
    "parse_last_event_id",
    "register_filters",
    "safe_href",
    "sse_response",
    "timestamp",
    "truncate_middle",
    "worst_status",
]
