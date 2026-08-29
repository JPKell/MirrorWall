"""Static assets: hashed URLs, cache headers, and two ways out of the root that both fail."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from mirrorwall import PACKAGE_STATIC_DIR, create_template_environment
from mirrorwall.static import (
    IMMUTABLE_CACHE_CONTROL,
    asset_digest,
    asset_url,
    mount_static,
    resolve_asset,
)


def test_the_url_carries_the_files_own_digest() -> None:
    url = asset_url("css/tokens.css")
    expected = hashlib.sha256((PACKAGE_STATIC_DIR / "css" / "tokens.css").read_bytes()).hexdigest()[
        :12
    ]
    assert url == f"/static/mirrorwall/css/tokens.css?v={expected}"


def test_a_changed_file_changes_the_url(tmp_path: Path) -> None:
    """The whole basis for caching a year: a new build is a new URL."""
    (tmp_path / "a.css").write_text("body{}")
    first = asset_digest("a.css", root=tmp_path)
    asset_digest.cache_clear()
    (tmp_path / "a.css").write_text("body{color:red}")
    assert asset_digest("a.css", root=tmp_path) != first
    asset_digest.cache_clear()


def test_a_missing_asset_falls_back_rather_than_failing_every_page(tmp_path: Path) -> None:
    assert asset_url("css/nope.css", root=tmp_path) == "/static/mirrorwall/css/nope.css"


@pytest.mark.parametrize(
    "path", ["../../../etc/passwd", "css/../../secrets.txt", "/etc/passwd", "css\\tokens.css"]
)
def test_traversal_is_refused_by_both_asset_url_and_resolve(path: str) -> None:
    with pytest.raises(ValueError, match="static root"):
        asset_url(path)
    with pytest.raises(ValueError, match="static root"):
        resolve_asset(path)

    # The Phase 1 filter and this hashing replacement are two implementations of one seam, so
    # they must refuse exactly the same inputs: a template whose output changed when an
    # application called mount_static would be the worst kind of surprise.
    from mirrorwall.filters import asset_url as plain_asset_url

    with pytest.raises(ValueError, match="static root"):
        plain_asset_url(path)


def test_a_symlink_out_of_the_root_is_refused(tmp_path: Path) -> None:
    """The escape a check written only against `..` lets through."""
    root = tmp_path / "static"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("secret")
    (root / "link.txt").symlink_to(outside)
    with pytest.raises(ValueError, match="static root"):
        resolve_asset("link.txt", root=root)


def test_a_contained_symlink_still_resolves(tmp_path: Path) -> None:
    root = tmp_path / "static"
    (root / "css").mkdir(parents=True)
    (root / "css" / "real.css").write_text("body{}")
    (root / "alias.css").symlink_to(root / "css" / "real.css")
    assert resolve_asset("alias.css", root=root).read_text() == "body{}"


def test_a_missing_asset_raises_file_not_found_not_value_error(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        resolve_asset("nope.css", root=tmp_path)


def _client() -> TestClient:
    app = Starlette()
    mount_static(app)
    return TestClient(app, base_url="http://localhost")


def test_a_hashed_request_is_immutable_and_a_bare_one_is_not() -> None:
    digest = asset_digest("css/tokens.css")
    with _client() as client:
        hashed = client.get(f"/static/mirrorwall/css/tokens.css?v={digest}")
        bare = client.get("/static/mirrorwall/css/tokens.css")
    assert hashed.status_code == 200
    assert hashed.headers["cache-control"] == IMMUTABLE_CACHE_CONTROL
    assert bare.status_code == 200
    assert bare.headers.get("cache-control") != IMMUTABLE_CACHE_CONTROL
    assert hashed.content == bare.content, "the digest is a cache key, never access control"


def test_traversal_over_http_is_refused() -> None:
    with _client() as client:
        assert client.get("/static/mirrorwall/../../../etc/passwd").status_code == 404


def test_mounting_registers_the_hashing_filter_so_no_template_changes() -> None:
    environment = create_template_environment(globals_={"product_name": "Example"})
    plain = environment.from_string("{{ 'css/tokens.css' | asset_url }}").render()
    assert "?v=" not in plain

    app = Starlette()
    mount_static(app, environment=environment)
    hashed = environment.from_string("{{ 'css/tokens.css' | asset_url }}").render()
    assert hashed.startswith("/static/mirrorwall/css/tokens.css?v=")


def test_an_application_can_mount_its_own_directories_too(tmp_path: Path) -> None:
    (tmp_path / "app.css").write_text("body{}")
    app = Starlette()
    mount_static(app, extra_dirs={"/static/app": tmp_path})
    with TestClient(app, base_url="http://localhost") as client:
        assert client.get("/static/app/app.css").status_code == 200
