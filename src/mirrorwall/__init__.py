"""MirrorWall — the shared UI and web-edge toolkit for the suite's three applications.

Design tokens, a layout shell, component macros, template filters, JSON and error envelopes, SSE
plumbing, request-ID and Host-validation middleware, static mounting and health primitives — so
FreeWeight, LoadCoach and IdeaPress look and behave like one product family without sharing a
single page.

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
    timestamp,
    truncate_middle,
)
from mirrorwall.templating import (
    DEFAULT_THEME_STORAGE_KEY,
    PACKAGE_STATIC_DIR,
    PACKAGE_TEMPLATE_DIR,
    create_template_environment,
)

__all__ = [
    "DEFAULT_THEME_STORAGE_KEY",
    "EM_DASH",
    "PACKAGE_STATIC_DIR",
    "PACKAGE_TEMPLATE_DIR",
    "STATIC_URL_PREFIX",
    "__version__",
    "asset_url",
    "bytes_human",
    "create_template_environment",
    "duration_human",
    "is_supported_test",
    "json_pretty",
    "measurement",
    "register_filters",
    "timestamp",
    "truncate_middle",
]
