"""mirrorwall.templating — the one Jinja environment every application's pages render through.

Built once per application, not per request: templates are compiled and cached on the environment,
so a per-request environment recompiles the layout on every page view and discards the cache that
makes the second view fast.

Two settings here are correctness, not preference:

* **Autoescaping** is on for HTML. A model name, a hostname and a provider's error message all
  reach a template from outside the process, and none of them are trusted markup.
* **``StrictUndefined``.** A missing variable raises rather than rendering blank. A blank where a
  number should be is exactly the failure ADR-0016 exists to prevent, arriving through the
  template layer instead of the measurement layer.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

from jinja2 import ChoiceLoader, Environment, FileSystemLoader, StrictUndefined, select_autoescape

from mirrorwall.filters import register_filters

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

__all__ = [
    "DEFAULT_THEME_STORAGE_KEY",
    "PACKAGE_STATIC_DIR",
    "PACKAGE_TEMPLATE_DIR",
    "create_template_environment",
]

PACKAGE_TEMPLATE_DIR: Final = Path(__file__).parent / "templates"
"""Where this package's own templates live. Package data, present in the built wheel."""

PACKAGE_STATIC_DIR: Final = Path(__file__).parent / "static"
"""Where this package's own CSS, JS and icons live. Package data, present in the built wheel."""

DEFAULT_THEME_STORAGE_KEY: Final = "mirrorwall-theme"
"""The ``localStorage`` key the theme bootstrap reads. An application overrides it so two
applications served from the same origin do not share one reader's choice."""

_DEFAULT_GLOBALS: Final[Mapping[str, Any]] = {
    "product_version": "",
    "page": "",
    "nav_items": (),
    "footer_text": "",
    "show_telemetry_bar": False,
    "language": "en",
    "theme_storage_key": DEFAULT_THEME_STORAGE_KEY,
}
"""Defaults for the base template's optional slots.

Under ``StrictUndefined`` an unset variable raises, which is right for an application's own data
and wrong for a shell slot an application deliberately declines to fill. These are the slots with
a meaningful "not supplied" rendering; ``product_name`` is not among them, because a shell with no
product name is a bug rather than a choice.
"""


def create_template_environment(
    *,
    app_template_dirs: Sequence[Path] = (),
    globals_: Mapping[str, Any] | None = None,
) -> Environment:
    """Build the Jinja environment an application renders its pages through.

    The application's own template directories come first on the search path, so a page named
    ``mirrorwall/base.html`` in an application overrides this package's — an escape hatch that
    costs nothing and prevents a fork.

    Args:
        app_template_dirs: The application's template directories, highest priority first.
        globals_: Values available to every template, e.g. ``product_name`` and ``nav_items``.
            Merged over this package's own defaults for the shell's optional slots.

    Returns:
        The environment: autoescaping on, ``StrictUndefined``, this package's macros on the search
        path, and the shared filters and the ``supported`` test registered.
    """
    environment = Environment(
        loader=ChoiceLoader(
            [
                FileSystemLoader([str(path) for path in app_template_dirs]),
                FileSystemLoader(str(PACKAGE_TEMPLATE_DIR)),
            ]
        ),
        autoescape=select_autoescape(default_for_string=True, default=True),
        undefined=StrictUndefined,
        auto_reload=False,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    register_filters(environment.filters, environment.tests)
    environment.globals.update(_DEFAULT_GLOBALS)
    if globals_:
        environment.globals.update(globals_)
    return environment
