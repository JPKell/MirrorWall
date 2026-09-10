"""The environment: StrictUndefined, autoescaping, the search path, and package data."""

from __future__ import annotations

from pathlib import Path

import pytest
from jinja2 import Environment, UndefinedError

from mirrorwall import (
    PACKAGE_STATIC_DIR,
    PACKAGE_TEMPLATE_DIR,
    create_template_environment,
)


def test_a_missing_variable_raises_rather_than_rendering_blank(environment: Environment) -> None:
    """A blank where a number should be is the failure ADR-0016 exists to prevent."""
    with pytest.raises(UndefinedError):
        environment.from_string("{{ never_supplied }}").render()


def test_content_containing_markup_renders_inert(environment: Environment) -> None:
    hostile = '<script>alert("x")</script> {{ 7*7 }} " \''
    rendered = environment.from_string("{{ value }}").render(value=hostile)
    assert "<script>" not in rendered
    assert "&lt;script&gt;" in rendered
    assert "49" not in rendered
    assert "&#34;" in rendered or "&quot;" in rendered


def test_an_application_template_directory_wins_over_the_packages_own(tmp_path: Path) -> None:
    override = tmp_path / "mirrorwall"
    override.mkdir()
    (override / "base.html").write_text("overridden")
    environment = create_template_environment(app_template_dirs=(tmp_path,))
    assert environment.get_template("mirrorwall/base.html").render() == "overridden"


def test_the_packages_own_templates_are_reachable_with_no_application_directories() -> None:
    environment = create_template_environment(globals_={"product_name": "Example"})
    assert environment.get_template("mirrorwall/components.html") is not None
    assert environment.get_template("mirrorwall/telemetry_bar.html") is not None


def test_shell_slots_have_defaults_but_the_product_name_does_not(environment: Environment) -> None:
    """A shell with no product name is a bug, not a deliberately empty slot."""
    assert environment.globals["nav_items"] == ()
    assert environment.globals["show_telemetry_bar"] is False
    bare = create_template_environment()
    with pytest.raises(UndefinedError):
        bare.get_template("mirrorwall/base.html").render()


def test_product_href_links_the_product_name_home_and_is_invisible_when_unset() -> None:
    environment = create_template_environment(globals_={"product_name": "Example"})
    base = environment.get_template("mirrorwall/base.html")
    linked = base.render(product_version="1.0", product_href="/")
    assert (
        '<h1><a class="brand" href="/">Example <span class="version">v1.0</span></a></h1>' in linked
    )
    # Unset, the heading is exactly the markup it was before the slot existed.
    plain = base.render(product_version="1.0")
    assert '<h1>Example <span class="version">v1.0</span></h1>' in plain
    assert 'class="brand"' not in plain


def test_every_shared_filter_and_the_supported_test_are_registered(
    environment: Environment,
) -> None:
    for name in (
        "bytes_human",
        "duration_human",
        "timestamp",
        "measurement",
        "truncate_middle",
        "json_pretty",
        "asset_url",
    ):
        assert name in environment.filters, name
    assert "supported" in environment.tests


def test_package_data_is_present_and_loadable_via_importlib_resources() -> None:
    """dev-plan P1 test list; the failure mode is package data missing from the wheel."""
    from importlib.resources import files

    root = files("mirrorwall")
    for relative in (
        "templates/mirrorwall/base.html",
        "templates/mirrorwall/components.html",
        "templates/mirrorwall/telemetry_bar.html",
        "static/css/tokens.css",
        "static/css/tokens.json",
        "static/js/theme.js",
        "static/icons/sprite.svg",
    ):
        resource = root.joinpath(relative)
        assert resource.is_file(), relative
        assert resource.read_text(encoding="utf-8")
    # PEP 561's marker is deliberately empty: its presence is the whole signal.
    assert root.joinpath("py.typed").is_file()

    assert PACKAGE_TEMPLATE_DIR.is_dir()
    assert PACKAGE_STATIC_DIR.is_dir()


def test_package_data_is_present_in_a_built_wheel(tmp_path: Path) -> None:
    """Configured artifacts are not the same claim as artifacts that shipped."""
    import subprocess
    import sys
    import zipfile

    project = Path(__file__).resolve().parents[2]
    result = subprocess.run(  # noqa: S603 — fixed argv, no shell, no user input
        [sys.executable, "-m", "hatchling", "build", "-t", "wheel"],
        cwd=project,
        capture_output=True,
        text=True,
        check=False,
        env={"PATH": "/usr/bin:/bin", "HATCH_BUILD_LOCATION": str(tmp_path)},  # noqa: E501
    )
    if result.returncode != 0:
        pytest.skip(f"hatchling build unavailable in this environment: {result.stderr[-200:]}")
    wheels = list(tmp_path.rglob("*.whl"))
    assert wheels, result.stdout
    with zipfile.ZipFile(wheels[0]) as archive:
        names = set(archive.namelist())
    for expected in (
        "mirrorwall/templates/mirrorwall/base.html",
        "mirrorwall/static/css/tokens.css",
        "mirrorwall/static/js/theme.js",
        "mirrorwall/static/icons/sprite.svg",
        "mirrorwall/py.typed",
    ):
        assert expected in names, expected
