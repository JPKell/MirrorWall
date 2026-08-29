# Changelog

All notable changes to `mirrorwall` are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows
[Semantic Versioning](https://semver.org/), pre-1.0 per
packaging and release standards §3.

## [Unreleased]

### Added
- Phase 1: design tokens, the layout shell and the core components, extracted from FreeWeight's
  shipped UI and generalized until nothing in the package knows what an application is.
  - `static/css/{tokens,reset,layout,components,tables,charts}.css` plus `tokens.json`. The
    palette is byte-identical to the one FreeWeight proved in production; `--mw-accent` and its
    three relatives are the per-application override point, and nothing else needs to change.
  - `templates/mirrorwall/{base,components,telemetry_bar}.html`: a shell of slots — header,
    navigation, telemetry bar, content, footer, theme bootstrap — and macros for button, input,
    select, checkbox, switch, card, table, badge, tabs, drawer, dialog, toast, tooltip, progress,
    empty state, pagination, filter bar, key-value list, JSON viewer and chart container.
  - `static/js/{theme,table,drawer,dialog,toast}.js`: progressive enhancement only. Every page is
    complete before any of them loads (ADR-0020).
  - `static/icons/sprite.svg`: sixteen original glyphs, stroked with `currentColor` so they
    re-theme with the page.
  - `templating.py`: `create_template_environment` — autoescaping on, `StrictUndefined`, the
    package's macros on the search path behind the application's own.
  - `filters.py`: `bytes_human`, `duration_human`, `timestamp`, `measurement`, `truncate_middle`,
    `json_pretty`, `asset_url`, and the `supported` test. `measurement` renders an em dash with
    the producer's own reason for an absent reading — never a zero (ADR-0016), and it is the only
    sanctioned way a template touches a `Measurement`, because `UNSUPPORTED` refuses `__bool__`.
  - `THIRD_PARTY_NOTICES.md` and `static/ASSETS.sha256`: the vendoring discipline, with every
    shipped asset's digest recomputed and checked by the test suite.
  - Tests: contrast computed from the tokens (4.5:1 text, 3:1 UI, both themes, 21 pairs each);
    a term scan over names and markup in every shipped file; component snapshots asserting the
    ARIA each pattern requires; escaping; `StrictUndefined`; package data present in a wheel that
    the test actually builds.

### Changed
- `.importlinter` used the plural `root_packages` with a bare string, which import-linter 2.x
  iterates character by character; and it lacked `include_external_packages`, required whenever a
  `forbidden` contract names modules outside the root package. Both fixed. `[tool.mypy]` gained
  `mypy_path`/`explicit_package_bases`, and the coverage floor moved from 85% to the 95% shared
  packages carry. (The same four defects were found and fixed in two other scaffolds this
  milestone; a scaffold from the same generator should be checked for them before its first gate.)
- Declared `anyio>=4,<5` directly. Phase 2's `sse_response` dispatches every call into the
  synchronous `EventSource` with `anyio.to_thread.run_sync` (ADR-0003 §6-8); Starlette pulls anyio
  in transitively, but a module this package imports directly is declared directly.
- Repository scaffold generated from the suite's development plan (no functional code yet).
