# Changelog

All notable changes to `mirrorwall` are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows
[Semantic Versioning](https://semver.org/), pre-1.0 per
packaging and release standards §3.

## [Unreleased]

### Changed
- Internal tightening with no behavioural change: both middleware rejections go through one
  error-response helper and the inline imports move to module scope; the hashed `asset_url` runs
  the plain filter's own path check instead of a second copy of it; `error_response` builds one
  body; `bytes_human` loses its unreachable branch. Module docstrings now count four applications,
  PromptCadence included.

### Added

- `tests/unit/test_readme_version.py` — asserts the version README.md states after its `Status:`
  line equals `__about__.__version__`, so a release cannot leave the README stale (M9 re-audit,
  row L7).

## [0.2.2] — 2026-09-04

### Changed
- **`setspec>=0.4,<0.7`**, widened from `<0.5`. The cap held the whole suite still: `mirrorwall` is
  a dependency of all four applications, so no application could move past `setspec` 0.4 while it
  stood — and two rows now need past it, PromptCadence P6 for `governance.egress_decision` (0.5)
  and FreeWeight 1.1 for `capability.evidence` 1.1 (0.6). It protected nothing in return. This
  package imports three names from `setspec` — `GeneratorInfo`, `SchemaVersion` and
  `dump_envelope`, all in `sse.py` — and all three are v1.0 payload surface, frozen under ADR-0009;
  0.5.0 and 0.6.0 are additive over it. The full suite passes unchanged against `setspec` 0.6.0 and
  no source change was needed, the same shape as 0.2.0's starlette widen. `requirements/ci.lock`
  moves to `setspec` 0.6.0 with it — and to `baseaicore` 0.4.1, which `setspec` 0.6.0 requires — so
  CI tests the versions a consumer will now resolve. No other pin in the lock moved.

## [0.2.1] — 2026-08-31

The two items LoadCoach's M5 verification recorded against this package (M5C-6, M5C-11), both of
which its pages carry commented stopgaps for.

### Added
- **`kv_list` items may carry an `href`**, rendering the value as a real anchor. The escaping
  contract holds: label and value stay escaped text whatever they contain — never HTML through
  the escaper, the M5 `| safe` lesson — and only the `href` becomes an attribute, through the new
  `safe_href` filter. `safe_href` (also published at package level — a deliberate contract
  addition to spec §7's surface) allowlists relative URLs and `http`/`https`/`mailto`, strips the
  characters browsers strip before scheme parsing (`java\tscript:` is `javascript:` to a
  browser), and refuses everything else with `None`, which the macro renders as the plain value
  with no anchor: a `javascript:` href is neutralized, never smuggled (M5C-6).
- **`.kv-list dd` wraps unbreakable tokens** (`overflow-wrap: anywhere` in `components.css`): a
  64-character machine fingerprint or a canonical model ID no longer widens the page at 375 px.
  Both LoadCoach stopgaps become deletable once this resolves (M5C-11).

## [0.2.0] — 2026-08-29

### Changed
- **`starlette>=1.3.1,<2`**, widened from `>=0.37,<1`. Two reasons, either sufficient. The 0.x line
  carries PYSEC-2026-161, -248, -249, -2280 and -2281, none of which has a fix below 1.3.1, so
  `pip-audit` fails the security gate against any lock the old cap allows. And the cap was wrong on
  its own terms: FreeWeight and LoadCoach — the two applications this package exists to serve —
  already run starlette 1.6 under fastapi 0.141, so `<1` made `mirrorwall` un-coinstallable with
  its own consumers. The full suite passes unchanged on 1.6.0; no source change was needed.
- CI installs from committed, hash-verified lockfiles (`requirements/ci.lock`,
  `requirements/release.lock`) rather than an editable checkout, per Packaging Standards §4;
  `pip-audit` audits those locks instead of an empty environment; `release.yml` gains the `pypi`
  deployment environment, the manual TestPyPI dry run required before a first release, and a build
  chain pinned byte-for-byte to the one the dry run proves. `[tool.coverage.run] source` now names
  the importable package rather than `src/mirrorwall`, because a non-editable install reports 0 %
  against a path-based source.

  The `dev` extra moves to `pytest>=9.0.3,<10`, matching BaseAiCore, SetSpec, ModelRack and
  SweatMeter: PYSEC-2026-1845 affects pytest through 9.0.2 and failed the security job.

  `ci.lock` could not be compiled at all until `setspec 0.4.0` was published: this package requires
  `setspec>=0.4,<0.5`, PyPI carried 0.3.0, and every CI job that installed from an index failed at
  the `pip install` step for that reason. Those jobs had never been green.

### Added
- `tests/contract/test_public_api.py`: the published surface asserted in both directions, every
  name resolved, `py.typed` shipped, and the templates, stylesheets, icon sprite and
  `PACKAGE_TEMPLATE_DIR`/`PACKAGE_STATIC_DIR` roots asserted against the *installed* package. A
  wheel that drops package data imports perfectly and then fails at a consumer's first render, so
  the check has to run against the install rather than the checkout. The `contracts` CI job
  collected nothing before this and failed with pytest's exit code 5.

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

- Phase 2: the backend helpers — envelopes, request IDs, SSE, static mounting, health.
  - `sse.py`: `Event`, `Subscription`, `EventBroker`, the `EventSource` protocol and
    `sse_response`. The stream **subscribes before it replays** and drops from the live queue
    anything the replay already emitted, which is what makes a reconnect gap-free and
    duplicate-free at once. Every call into the synchronous, database-backed source — opening the
    subscription, each bounded replay batch, closing it — goes through `anyio.to_thread.run_sync`
    (ADR-0003 §6-8); the steady-state stream is served from the in-memory fan-out and takes no
    threadpool slot at all, which is what makes 200 concurrent subscribers affordable against a
    40-thread pool. Subscriber queues are bounded and drop the oldest, counting what they dropped.
    Every frame carries the SetSpec event envelope except `event: token`, which is bare — the one
    documented exception (ADR-0025 §3).
  - `middleware.py`: `RequestIdMiddleware` (validate or generate, bind to the logging context,
    echo `X-Request-ID`, add `X-Response-Time-Ms`), `HostValidationMiddleware` and
    `CsrfMiddleware` (ADR-0026 §1-2), both running before routing and before authentication.
  - `responses.py`: `json_response`, `error_response`, `paginated_response`, `clamp_limit`.
  - `static.py`: `mount_static` and a content-hashing `asset_url` that replaces the Phase 1
    filter at the same template seam, with immutable cache headers, traversal **and** symlink
    containment.
  - `health.py`: `ComponentStatus`, `ComponentHealth`, `health_payload`, `worst_status`.
    `NOT_CONFIGURED` never worsens a roll-up: a component nobody asked for is not a fault.
  - `static/js/{sse,telemetry}.js`: the client half. Events are applied idempotently by sequence,
    so a reconnect's redelivered boundary event does not duplicate a row; an absent telemetry
    reading renders an em dash with its reason, never `0`.
  - `sse_response(..., terminal_events=...)`: a finite stream — a generation, a benchmark run —
    closes after its own last event instead of holding a connection open for a producer that has
    nothing left to say. Empty by default, because an open-ended stream has no such event.
  - Every SSE property is proved by mutation: replay-before-subscribe, a missing dedupe, a
    blocking `replay`, an unbounded queue and a missing cleanup were each applied to the module
    and each confirmed to fail the corresponding test before it was considered finished.

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
