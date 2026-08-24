# MirrorWall

Design tokens, layout, component macros, SSE and JSON/error envelope helpers so three applications look like one family without sharing a page.

**Status:** specified, not yet implemented. This repository currently holds the project scaffold
(directory structure, tooling configuration, and the project documentation) —
see [development plan](docs/packages/mirrorwall/development-plan.md) for what each phase adds.

Part of the **Local AI Suite**.

## Install

```bash
pip install mirrorwall
```

## Quickstart

```python
import mirrorwall
```

See [docs/packages/mirrorwall/spec.md](docs/packages/mirrorwall/spec.md) §20 for a runnable example.

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
