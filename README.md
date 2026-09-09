# MirrorWall

Design tokens, layout, component macros, SSE and JSON/error envelope helpers so the suite's applications look like one family without sharing a page.

**Status:** `0.3.0` (prepared, unpublished) — Phases 1–4: design tokens, the layout shell, the
component macros, template filters, JSON and error envelopes, request-ID/Host/CSRF middleware,
SSE with a gap-free replay-to-live handoff, static mounting with content-hashed URLs, the health
primitives, and Phase 4's dense-console tokens (`status_dot`, `app_tab`, `meter`, `log_pane`,
`side_nav`, a `figure` card, dense/mono tables) with htmx vendored opt-in per page (ADR-0128).
LoadCoach renders every page on `0.2.2`; nothing above changes its rendering until it opts in.
See the [development plan](docs/packages/mirrorwall/development-plan.md).

Part of the **Local AI Suite**.

## Install

```bash
pip install mirrorwall
```

## Quickstart

```python
from pathlib import Path

from mirrorwall import create_template_environment, mount_static

environment = create_template_environment(
    app_template_dirs=(Path("src/yourapp/web/templates"),),
    globals_={
        "product_name": "YourApp",
        "product_version": "1.0.0",
        "nav_items": ({"key": "home", "href": "/", "label": "Home"},),
        "theme_storage_key": "yourapp-theme",
    },
)
mount_static(app, environment=environment)  # your Starlette/FastAPI application
```

Then a page is four lines:

```jinja
{% extends "mirrorwall/base.html" %}
{% from "mirrorwall/components.html" import table %}
{% block content %}{{ table(columns, rows, table_id="things", sortable=true) }}{% endblock %}
```

Streaming, with the replay-to-live handoff, heartbeats and thread dispatch handled for you:

```python
from mirrorwall import sse_response

return sse_response(
    your_event_source,
    stream_id=job_id,
    last_event_id=request.headers.get("last-event-id"),
    generator=GeneratorInfo(name="yourapp", version=__version__),
    terminal_events=frozenset({"result", "error"}),
)
```

See [docs/packages/mirrorwall/spec.md](docs/packages/mirrorwall/spec.md) §20 for the full surface.

## Documentation

Project documentation lives under [`docs/`](docs/README.md). Start with [`docs/README.md`](docs/README.md).

| Read this | For |
|---|---|
| [docs/packages/mirrorwall/spec.md](docs/packages/mirrorwall/spec.md) | Purpose, scope, non-goals, public contracts, configuration, acceptance criteria |
| [docs/packages/mirrorwall/development-plan.md](docs/packages/mirrorwall/development-plan.md) | The phased build plan: goals, work, tests, acceptance criteria per phase |

## Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pre-commit install
pytest -m "not live and not performance"
```

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the full workflow and [`SECURITY.md`](SECURITY.md) for
how to report a vulnerability.

## License

Apache-2.0 — see [`LICENSE`](LICENSE).
