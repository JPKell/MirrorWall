"""Shared fixtures: an environment built the way an application builds one."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from mirrorwall import create_template_environment

if TYPE_CHECKING:
    from jinja2 import Environment


@pytest.fixture
def environment() -> Environment:
    """A MirrorWall environment with no application templates on the path."""
    return create_template_environment(globals_={"product_name": "Example"})
