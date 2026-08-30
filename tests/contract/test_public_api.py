"""Contract: mirrorwall's published surface, in both directions.

Spec §7 fixes the public API and §11 fixes what a consumer may rely on. Both are promises to three
applications that render their entire UI through this package, so both are asserted here rather
than left to review: a name silently added to ``__all__`` is as much a contract change as one
silently removed.

The package data is asserted too, which the other shared packages have no equivalent of. MirrorWall
ships templates, stylesheets, scripts and an icon sprite as *data*; a packaging change that drops
them produces a wheel that imports perfectly and then fails at the first render, in the consumer,
at runtime.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

import mirrorwall

pytestmark = pytest.mark.contract

# The published surface. Spec §7's Python block names the core of it — templating, responses,
# streaming, middleware, mounting and the health primitives — and the constants and filters below
# are the rest of what `__init__.py` exports. Editing this list is a deliberate contract change and
# belongs in CHANGELOG.md under the version that makes it.
_PUBLISHED_NAMES = frozenset(
    {
        "CSRF_COOKIE_NAME",
        "CSRF_FIELD_NAME",
        "ComponentHealth",
        "ComponentStatus",
        "CsrfMiddleware",
        "DEFAULT_PAGE_LIMIT",
        "DEFAULT_THEME_STORAGE_KEY",
        "EM_DASH",
        "Event",
        "EventBroker",
        "EventSource",
        "HashedStaticFiles",
        "HostValidationMiddleware",
        "MAX_PAGE_LIMIT",
        "PACKAGE_STATIC_DIR",
        "PACKAGE_TEMPLATE_DIR",
        "RequestIdMiddleware",
        "STATIC_URL_PREFIX",
        "Subscription",
        "TOKEN_EVENT",
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
        "sse_response",
        "timestamp",
        "truncate_middle",
        "worst_status",
    }
)

# Every file a consumer's first render reaches for. The full trees are larger; these are the ones
# whose absence is not a degraded page but an exception.
_REQUIRED_PACKAGE_DATA = (
    "templates/mirrorwall/base.html",
    "templates/mirrorwall/components.html",
    "templates/mirrorwall/telemetry_bar.html",
    "static/css/tokens.css",
    "static/css/tokens.json",
    "static/css/reset.css",
    "static/css/layout.css",
    "static/css/components.css",
    "static/js/theme.js",
    "static/icons/sprite.svg",
)


def _package_root() -> Path:
    return Path(inspect.getfile(mirrorwall)).parent


def test_the_published_surface_is_exactly_what_the_spec_names() -> None:
    """Both directions: nothing removed, and nothing added without a contract change."""
    assert set(mirrorwall.__all__) == _PUBLISHED_NAMES


def test_every_published_name_actually_resolves() -> None:
    """An `__all__` entry with no attribute behind it breaks `from mirrorwall import *` silently."""
    missing = [name for name in mirrorwall.__all__ if not hasattr(mirrorwall, name)]
    assert missing == []


def test_the_published_surface_has_no_duplicates() -> None:
    """`__all__` is grouped in import order, not `sorted()` order, so length is the check."""
    assert len(mirrorwall.__all__) == len(set(mirrorwall.__all__))


def test_the_package_ships_a_pep_561_marker() -> None:
    """Without it a consumer's `mypy --strict` reports every mirrorwall import as untyped."""
    assert (_package_root() / "py.typed").is_file()


@pytest.mark.parametrize("relative_path", _REQUIRED_PACKAGE_DATA)
def test_the_package_ships_its_templates_and_static_assets(relative_path: str) -> None:
    """A wheel that drops package data imports cleanly and fails at the consumer's first render."""
    assert (_package_root() / relative_path).is_file()


def test_the_template_and_static_roots_point_inside_the_installed_package() -> None:
    """`PACKAGE_TEMPLATE_DIR`/`PACKAGE_STATIC_DIR` are what a consumer adds to its search path.

    Resolved from the installed location, not from a source checkout: a path that only exists in
    the repository is a working editable install and a broken wheel.
    """
    root = _package_root()
    assert mirrorwall.PACKAGE_TEMPLATE_DIR.is_dir()
    assert mirrorwall.PACKAGE_STATIC_DIR.is_dir()
    assert mirrorwall.PACKAGE_TEMPLATE_DIR.resolve() == (root / "templates").resolve()
    assert mirrorwall.PACKAGE_STATIC_DIR.resolve() == (root / "static").resolve()


def test_the_version_is_a_plain_release_string() -> None:
    """Packaging standards: the version is read from `__about__.py`, and the wheel carries it."""
    assert mirrorwall.__version__.count(".") == 2
    assert all(part.isdigit() for part in mirrorwall.__version__.split("."))
