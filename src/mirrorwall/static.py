"""mirrorwall.static — mounting this package's assets, with content-hashed, cacheable URLs.

Assets are served from the installed package. There is no CDN and no network request at page load
(spec §14), which is what makes the applications work on a machine with no internet — the same
machine that is running a local model precisely so nothing leaves it.

Content hashing is what lets those assets be cached forever and still change on the next release:
the URL contains a digest of the file, so a new build is a new URL and no reader is ever served a
stylesheet that disagrees with the markup it styles.
"""

from __future__ import annotations

import hashlib
import os
import posixpath
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Final

from starlette.responses import Response
from starlette.staticfiles import StaticFiles

from mirrorwall.filters import STATIC_URL_PREFIX
from mirrorwall.filters import asset_url as plain_asset_url
from mirrorwall.templating import PACKAGE_STATIC_DIR

if TYPE_CHECKING:
    from collections.abc import Mapping
    from os import PathLike

    from jinja2 import Environment
    from starlette.applications import Starlette
    from starlette.types import Scope

__all__ = [
    "IMMUTABLE_CACHE_CONTROL",
    "HashedStaticFiles",
    "asset_digest",
    "asset_url",
    "mount_static",
    "resolve_asset",
]

IMMUTABLE_CACHE_CONTROL: Final = "public, max-age=31536000, immutable"
"""A year, immutable. Safe only because the URL carries the file's own digest: change the file and
the URL changes, so nothing stale can be served under a name that still resolves."""

_DIGEST_LENGTH: Final = 12


def resolve_asset(relative: str, *, root: Path = PACKAGE_STATIC_DIR) -> Path:
    """Resolve an asset path against ``root``, refusing anything that escapes it.

    Both traversal and symlink escape are refused, and both are checked after full resolution:
    ``../`` is the obvious attack, and a symlink pointing outside the root is the one that gets
    past a check written only against ``..``.

    Args:
        relative: A path relative to the static root, e.g. ``"css/tokens.css"``. An absolute path
            is refused rather than reinterpreted, matching
            :func:`mirrorwall.filters.asset_url`'s rule exactly: the two implementations of this
            seam must answer identically, or a template's output changes when an application
            calls :func:`mount_static`.
        root: The static root.

    Returns:
        The resolved absolute path.

    Raises:
        ValueError: The path is absolute, escapes the root, or resolves outside it.
        FileNotFoundError: No such asset.
    """
    cleaned = relative.strip()
    if cleaned.startswith("/") or "\\" in cleaned or posixpath.normpath(cleaned).startswith(".."):
        message = f"asset path escapes the static root: {relative!r}"
        raise ValueError(message)
    resolved = (root / posixpath.normpath(cleaned)).resolve()
    if not resolved.is_relative_to(root.resolve()):
        message = f"asset path escapes the static root: {relative!r}"
        raise ValueError(message)
    if not resolved.is_file():
        message = f"no such asset: {relative!r}"
        raise FileNotFoundError(message)
    return resolved


@lru_cache(maxsize=512)
def asset_digest(relative: str, *, root: Path = PACKAGE_STATIC_DIR) -> str:
    """Return the short content digest that goes into an asset's URL.

    Cached: the files are package data and cannot change while the process runs, so hashing them
    once per process is correct rather than merely fast.

    Args:
        relative: A path relative to the static root.
        root: The static root.

    Returns:
        The first twelve hex characters of the file's SHA-256.

    Raises:
        ValueError: The path escapes the root.
        FileNotFoundError: No such asset.
    """
    return hashlib.sha256(resolve_asset(relative, root=root).read_bytes()).hexdigest()[
        :_DIGEST_LENGTH
    ]


def asset_url(
    path: str, *, prefix: str = STATIC_URL_PREFIX, root: Path = PACKAGE_STATIC_DIR
) -> str:
    """Return the content-hashed URL an asset is served from.

    Replaces :func:`mirrorwall.filters.asset_url`'s plain form. The seam is the function's name
    and signature, so no template changes when an application registers this one instead — which
    :func:`mount_static` does for it.

    An asset that does not exist falls back to the un-hashed URL rather than raising: a missing
    stylesheet should render an ugly page a developer immediately notices, not a 500 on every
    page in the application.

    Args:
        path: A path relative to the static root, e.g. ``"css/tokens.css"``.
        prefix: The URL the static mount serves from.
        root: The static root.

    Returns:
        ``{prefix}/{path}?v={digest}``.

    Raises:
        ValueError: ``path`` is absolute or escapes the static root — that is a template bug, not
            a missing file, and it is never rendered as a URL. The check is
            :func:`mirrorwall.filters.asset_url`'s own, so the two forms cannot disagree.
    """
    plain = plain_asset_url(path, prefix=prefix)  # the same refusals, by construction
    try:
        digest = asset_digest(plain.removeprefix(f"{prefix}/"), root=root)
    except FileNotFoundError:
        return plain
    return f"{plain}?v={digest}"


class HashedStaticFiles(StaticFiles):
    """``StaticFiles`` that marks a digest-carrying request immutable.

    A request with the right ``?v=`` digest is cacheable for a year; one without is revalidated
    normally. Both serve the same bytes — the digest is a cache key, never an access control.
    """

    def file_response(
        self,
        full_path: str | PathLike[str],
        stat_result: os.stat_result,
        scope: Scope,
        status_code: int = 200,
    ) -> Response:
        """Serve the file, adding the immutable cache header when the URL carried a digest."""
        response = super().file_response(full_path, stat_result, scope, status_code)
        if b"v=" in scope.get("query_string", b""):
            response.headers["Cache-Control"] = IMMUTABLE_CACHE_CONTROL
        return response


def mount_static(
    app: Starlette,
    *,
    prefix: str = STATIC_URL_PREFIX,
    extra_dirs: Mapping[str, Path] | None = None,
    environment: Environment | None = None,
) -> None:
    """Mount this package's assets, and any the application adds, with hashed URLs.

    Args:
        app: The Starlette or FastAPI application.
        prefix: Where this package's own assets are served from.
        extra_dirs: The application's own static directories, keyed by URL prefix.
        environment: The Jinja environment to register the hashing ``asset_url`` filter on. When
            given, every template that already writes ``{{ 'css/tokens.css' | asset_url }}``
            starts emitting hashed URLs with no template change at all.
    """
    app.mount(prefix, HashedStaticFiles(directory=PACKAGE_STATIC_DIR), name="mirrorwall-static")
    for extra_prefix, directory in (extra_dirs or {}).items():
        app.mount(
            extra_prefix,
            HashedStaticFiles(directory=directory),
            name=f"static-{extra_prefix.strip('/').replace('/', '-')}",
        )
    if environment is not None:
        environment.filters["asset_url"] = asset_url
