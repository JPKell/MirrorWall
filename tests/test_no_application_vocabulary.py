"""The term scan: no application vocabulary anywhere in this package.

The named risk for this extraction is dragging FreeWeight's *pages* out along with its components
(dev-plan P1). A component with a `run_id` parameter or a `.benchmark-row` class is not a shared
component; it is FreeWeight's page wearing a macro's clothes, and the second application it is
offered to will fork it.

The scan covers every shipped file — Python, templates, CSS, JavaScript, SVG — because the
vocabulary can leak into a class name or a module name as easily as into an identifier.

It scans **names and markup**, with comments and docstrings stripped first. That is deliberate and
it is not a loophole: a `.benchmark-row` selector or a `run_id` macro parameter is the defect this
test exists to catch, while a docstring saying "this package knows nothing about benchmarks,
routing or content" is the boundary being documented rather than a breach of it. Prose that names
the three consumers is likewise correct — spec §6 names them — and prose ships no behaviour.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src" / "mirrorwall"

APPLICATION_NAMES = ("freeweight", "loadcoach", "ideapress")

# Vocabulary belonging to one application's problem domain, not to a UI toolkit. Each is matched
# as a whole word, case-insensitively.
APPLICATION_VOCABULARY = (
    # FreeWeight: measurement and grading
    "benchmark",
    "benchmarks",
    "goal",
    "goals",
    "grading",
    "grader",
    "rubric",
    "judgement",
    "leaderboard",
    "evidence",
    # LoadCoach: routing and execution
    "routing",
    "candidate",
    "fallback",
    "queue",
    "lease",
    "job",
    "jobs",
    "attempt",
    "provider",
    "residency",
    # IdeaPress: content
    "article",
    "draft",
    "workflow",
    "byline",
)

SCANNED_SUFFIXES = (".py", ".html", ".css", ".js", ".json", ".svg", ".txt")


def _strip_python(text: str) -> str:
    """Remove comments and docstrings, keeping every other string literal and every name.

    Both passes work from the *original* text's line and column numbers, so one cannot shift the
    other's positions — the mistake that makes a stripper silently stop stripping.
    """
    import ast
    import io
    import tokenize

    lines = text.splitlines()

    try:
        for token in tokenize.generate_tokens(io.StringIO(text).readline):
            if token.type != tokenize.COMMENT:
                continue
            row = token.start[0] - 1
            lines[row] = lines[row][: token.start[1]]
    except tokenize.TokenError:  # pragma: no cover — the file would not import either
        pass

    try:
        tree = ast.parse(text)
    except SyntaxError:  # pragma: no cover — the file would not import either
        return "\n".join(lines)
    # Every standalone string expression statement, not only a function's or a class's first
    # one: PEP 258 attribute docstrings — the bare string under a module-level constant — are
    # prose too, and this package uses them for every public constant. A string that is *used*
    # (assigned, passed, returned) is not an expression statement and survives, which is what
    # keeps a class name or a CSS selector in a string literal inside the scan.
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
            and node.end_lineno is not None
        ):
            for index in range(node.lineno - 1, min(node.end_lineno, len(lines))):
                lines[index] = ""
    return "\n".join(lines)


def _strip_block_comments(text: str) -> str:
    text = re.sub(r"\{#.*?#\}", "", text, flags=re.S)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", "", text)


def _strip_json_comments(text: str) -> str:
    import json

    def prune(value: object) -> object:
        if isinstance(value, dict):
            return {k: prune(v) for k, v in value.items() if not k.startswith("$")}
        if isinstance(value, list):
            return [prune(item) for item in value]
        return value

    return json.dumps(prune(json.loads(text)))


def scannable(path: Path) -> str:
    """Return the file's names and markup, with comments and docstrings removed."""
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".py":
        return _strip_python(text)
    if path.suffix == ".json":
        return _strip_json_comments(text)
    return _strip_block_comments(text)


def _shipped_files() -> list[Path]:
    return sorted(
        path
        for path in SOURCE_ROOT.rglob("*")
        if path.is_file() and path.suffix in SCANNED_SUFFIXES and "__pycache__" not in path.parts
    )


def test_the_scan_actually_covers_the_package() -> None:
    """A scan over an empty file list passes for the wrong reason."""
    files = _shipped_files()
    assert len(files) >= 15
    suffixes = {path.suffix for path in files}
    assert {".py", ".html", ".css", ".js", ".json", ".svg"} <= suffixes


def test_the_stripper_removes_comments_and_docstrings_and_nothing_else() -> None:
    """The scan is only as strict as what survives stripping."""
    python = _strip_python(
        '''"""A docstring mentioning benchmark."""\nx = "benchmark_literal"  # benchmark\n'''
    )
    assert "docstring mentioning" not in python
    assert "# benchmark" not in python
    assert "benchmark_literal" in python, "a string literal is a name, not prose"

    attribute_doc = _strip_python('X = 1\n"""An attribute docstring mentioning benchmark."""\n')
    assert "attribute docstring" not in attribute_doc, "PEP 258 attribute docstrings are prose"
    assert "X = 1" in attribute_doc

    assert "hidden" not in _strip_block_comments("{# hidden #}<p>kept</p>")
    assert "kept" in _strip_block_comments("{# hidden #}<p>kept</p>")
    assert "hidden" not in _strip_block_comments("/* hidden */ .kept {}")
    assert "hidden" not in _strip_block_comments("// hidden\nvar kept = 1;")
    assert "kept" in _strip_block_comments("// hidden\nvar kept = 1;")


@pytest.mark.parametrize("path", _shipped_files(), ids=lambda path: path.name)
def test_no_application_name_appears_in_a_shipped_file(path: Path) -> None:
    text = scannable(path).lower()
    found = [name for name in APPLICATION_NAMES if name in text]
    assert not found, f"{path} mentions {found}"


@pytest.mark.parametrize("path", _shipped_files(), ids=lambda path: path.name)
def test_no_application_vocabulary_appears_in_a_shipped_file(path: Path) -> None:
    text = scannable(path)
    pattern = re.compile(r"\b(" + "|".join(APPLICATION_VOCABULARY) + r")\b", re.IGNORECASE)
    found = sorted({match.group(0).lower() for match in pattern.finditer(text)})
    assert not found, f"{path} uses application vocabulary: {found}"


def test_no_component_macro_has_an_application_shaped_required_parameter() -> None:
    """The plan's named failure mode: 'components with FreeWeight-shaped required parameters'.

    A macro's required parameters are the ones with no default. Every one of them must be a
    generic presentation word — a label, a set of columns, an element id — never a domain noun.
    """
    macros = (SOURCE_ROOT / "templates" / "mirrorwall" / "components.html").read_text()
    generic = {
        "label",
        "value",
        "name",
        "options",
        "items",
        "columns",
        "rows",
        "message",
        "payload",
        "text",
        "description",
        "title",
        "chart_id",
        "drawer_id",
        "dialog_id",
        "table_id",
    }
    for signature in re.findall(r"\{% macro (\w+)\(([^)]*)\)", macros):
        macro_name, parameters = signature
        required = [
            parameter.strip()
            for parameter in parameters.split(",")
            if parameter.strip() and "=" not in parameter
        ]
        unexpected = [parameter for parameter in required if parameter not in generic]
        assert not unexpected, f"macro {macro_name} requires non-generic {unexpected}"
