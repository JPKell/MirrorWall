# MirrorWall — Development Plan

**Sequence position:** extracted during **LoadCoach Phase 4**, from FreeWeight's web layer
([ADR-0011](../../adr/0011-shared-package-boundaries.md)). FreeWeight adopts it in FreeWeight
Phase 12.
**Target:** `mirrorwall 0.2.0` by the end of Phase 3.
**Reached; `0.2.2` is published** — the pin widen of row E5, with no behaviour change.
**Phase 4 target:** `mirrorwall 0.3.0`, row WM (WeightRoomGym design brief). **Reached; prepared,
not published** — gates A–C below.

**Precondition for starting:** FreeWeight has a complete, polished UI in production use, and LoadCoach
needs the same shell, components and streaming. The components have therefore been designed against
one real application and are about to be validated against a second — which is the only honest moment
to extract a UI toolkit.

---

## Phase 1 — Tokens, layout shell and core components

**Goal:** LoadCoach renders its first page using MirrorWall's shell and components, and it looks like
FreeWeight without containing any FreeWeight concept.

**Prerequisites:** FreeWeight P11 complete (a shipped UI); `baseaicore`, `setspec`.

**Work**
* Repository skeleton with package data configured for templates, CSS, JS and vendored assets.
* Move and generalize from FreeWeight: `tokens.css`/`tokens.json` (accent parameterized), reset,
  layout CSS, base template (header slot, telemetry bar slot, content block, theme bootstrap),
  and the component macros listed in the [spec](spec.md) §4.
* Vendored assets: charting library, Inter font with its licence, inline SVG icon set, with a
  `THIRD_PARTY_NOTICES.md` and SHA-256 records.
* `create_template_environment` with shared filters: `bytes_human`, `duration_human`, `timestamp`,
  `measurement` (renders `—` plus reason for `UNSUPPORTED`), `truncate_middle`, `json_pretty`.
* Term scan test: no application vocabulary anywhere in the package.

**Files/subsystems**
```text
src/mirrorwall/{__init__,__about__,templating,filters}.py
src/mirrorwall/templates/mirrorwall/{base.html,components.html,telemetry_bar.html}
src/mirrorwall/static/{css/{tokens,reset,layout,components,tables,charts}.css,
                       js/{theme,table,drawer,dialog,toast}.js,
                       vendor/**,fonts/**,icons/**}
tests/unit/{test_templating,test_filters}.py
tests/snapshot/test_components.py
tests/test_no_application_vocabulary.py
```

**Tests**
* Snapshot render of every component in light and dark; required ARIA attributes present.
* `measurement` filter renders `—` with a tooltip for `UNSUPPORTED` and never `0`.
* `StrictUndefined`: a missing variable raises rather than rendering blank.
* Escaping: content containing `<script>`, `{{ }}` and quotes renders inert.
* Contrast: every token pair meets 4.5:1 (text) / 3:1 (UI) in both themes.
* Term scan finds no application vocabulary.
* Package data present in the built wheel and loadable via `importlib.resources`.

**Acceptance criteria**
1. LoadCoach renders a real page (its Models list) with MirrorWall's shell and table.
2. FreeWeight's existing look is reproduced by tokens alone, with only the accent differing.
3. Coverage ≥ 95 %; strict typing clean.

**Known risks:** extracting FreeWeight's *pages* along with its components. Mitigated by the term-scan
test and by building against LoadCoach first.
**Likely failure modes:** components with FreeWeight-shaped required parameters; package data missing
from the wheel.
**Gold standards:** no application vocabulary; accessible components; offline assets.
**Deferred:** SSE, envelopes, telemetry-bar JS, FreeWeight adoption.

---

## Phase 2 — Backend helpers: envelopes, request IDs, SSE, static

**Goal:** both applications share one streaming and JSON convention, and a browser that disconnects
loses nothing.

**Prerequisites:** Phase 1.

**Work**
* `responses.py`: `json_response`, `error_response`, `paginated_response`, built on SetSpec models.
* `middleware.py`: `RequestIdMiddleware` — validate or generate, bind to the logging context, echo in
  `X-Request-ID`, add `X-Response-Time-Ms`.
* `sse.py`: `EventSource` protocol and `sse_response` — subscribe-before-replay, dedupe by sequence,
  bounded queue with drop, heartbeat, terminal event on source failure, clean close on disconnect.
  **Every call into the (synchronous, database-backed) `EventSource` is dispatched with
  `anyio.to_thread.run_sync`**, here and only here, so no application can put a blocking `SELECT` on
  the event loop ([ADR-0003 §6–8](../../adr/0003-sync-vs-async-strategy.md)). Replay reads in bounded
  batches; the steady-state stream is served from the in-memory fan-out without touching the database.
* Frame shape: the SetSpec event envelope with the event as `payload`, except `event: token`, which is
  bare — the one documented exception ([ADR-0025 §3](../../adr/0025-envelope-boundaries.md)).
* `middleware.py` also carries `HostValidationMiddleware` and `CsrfMiddleware`
  ([ADR-0026](../../adr/0026-local-http-hardening.md)), shared so all four applications behave
  identically and the check runs before routing and before authentication.
* `static.py`: `mount_static`, `asset_url` with content hashing, cache headers, containment checks.
* `health.py`: `ComponentStatus`, `ComponentHealth`, `health_payload`, `worst_status`.

**Files/subsystems**
```text
src/mirrorwall/{responses,middleware,sse,static,health}.py
src/mirrorwall/static/js/{sse.js,telemetry.js}
tests/unit/{test_responses,test_middleware,test_static,test_health}.py
tests/integration/test_sse.py
tests/js/test_sse_client.py            # DOM harness
```

**Tests**
* SSE: ordered delivery; replay from `Last-Event-ID` with no gap and no duplicate across the
  replay/live handoff; heartbeat at the configured cadence; slow consumer dropped once its queue
  fills; source exception yields a terminal event; 200 concurrent subscribers within the memory
  budget.
* Client module: reconnects after a drop, sends `Last-Event-ID`, and applies events idempotently.
* Envelopes validate against SetSpec models; `request_id` present on success and error paths.
* Request ID: a hostile header value (too long, control characters) is rejected and replaced.
* `Host`: an allowed value passes, a disallowed one gets 421 before routing, and the check runs before
  any authentication dependency.
* CSRF: a forged form post is rejected; a valid one succeeds; a cross-origin JSON post is rejected.
* SSE threading: an `EventSource` whose `replay` blocks for 200 ms does not delay the event loop,
  measured with a lag probe — the test that keeps the async edge honest.
* Frame shape: every non-`token` frame parses through `setspec.load_envelope`; `token` does not.
* Static: hashed URL, cache headers, traversal refused, symlink escape refused.

**Acceptance criteria**
1. A browser refresh mid-stream resumes with no missing or duplicated event.
2. Both applications produce byte-compatible error envelopes.
3. Memory per idle subscriber within budget under a 200-subscriber test.

**Known risks:** the replay/live handoff is the subtlest code in the package. Mitigated by porting the
proven approach (subscribe before replay, dedupe by sequence) and testing it under injected races.
**Likely failure modes:** duplicated events at the handoff; unbounded queues; a heartbeat that keeps a
dead connection open forever.
**Gold standards:** gap-free replay; bounded memory; identical envelopes across applications.
**Deferred:** the interactive table/chart JS; FreeWeight adoption.

---

## Phase 3 — Interactive modules, accessibility hardening, publication

**Goal:** dense data views are usable and accessible in both applications, and the package ships.

**Prerequisites:** Phases 1–2.

**Work**
* JS modules: `table.js` (sort over the full dataset via the API, filter, column visibility,
  persistence), `drawer.js`, `dialog.js` (focus trap and restore), `toast.js`, `theme.js`,
  `charts.js` (chart container, theming, accessible table alternative), `telemetry.js`
  (bar updates without layout shift).
* Accessibility pass: keyboard traversal, focus management, live regions, reduced-motion support,
  skip link.
* Performance tests: render time, table sort, JS payload size.
* Component gallery page for development mode.
* README, component documentation with usage examples; publish `mirrorwall 0.2.0`.
* Write the adoption checklist FreeWeight Phase 12 follows.

**Files/subsystems**
```text
src/mirrorwall/static/js/{table,charts}.js
src/mirrorwall/gallery.py               # dev-mode component gallery
tests/js/{test_table,test_theme,test_telemetry}.py
tests/performance/test_render.py
tests/accessibility/test_keyboard_and_aria.py
docs/{components.md,adoption-checklist.md}
```

**Tests**
* Table: sort/filter/column visibility; preferences persist; sort applies to the whole dataset, not
  the page; 1 000-row sort within budget.
* Dialog/drawer: focus trapped, `Esc` closes, focus restored, `aria-modal` correct.
* Telemetry bar: updates with zero layout shift (asserted on measured widths); `—` for unsupported.
* Charts: re-theme on toggle; accessible table alternative present; units in tooltips.
* Reduced motion: transitions disabled when the media query matches.
* JS payload size within budget; no external URL in any asset.

**Acceptance criteria**
1. Every §20 criterion in the [spec](spec.md) is met.
2. LoadCoach's full UI runs on MirrorWall.
3. Both applications' page suites render against the release candidate in CI, obtained from their
   published distributions as a **test-only** dependency of MirrorWall's `dev` extra — never by
   importing application code, which `lint-imports` continues to forbid
   ([Testing Standards §8](../../standards/testing-standards.md)).
4. `mirrorwall 0.2.0` published; the adoption checklist is written and reviewed.

**Known risks:** JS complexity growing past the "islands" budget. Mitigated by the size budget being a
CI gate and by pushing logic into Python where possible.
**Likely failure modes:** components that only work with LoadCoach's data shapes; accessibility
regressions in later changes (mitigated by the automated a11y suite).
**Gold standards:** upgradeable without page changes; accessible; offline; no application vocabulary;
≥ 95 % coverage.
**Deferred:** chart-spec wrapper, print stylesheet, density modes, additional icons.

---

## Phase 4 — WeightRoomGym design brief: dense-console tokens and seven generic components

**Goal:** WeightRoomGym (row W3+) can build its shell, telemetry strip, log panes and left menu
entirely from MirrorWall macros, with every existing application still rendering byte-identically
until it opts in.

**Prerequisites:** Phases 1–3; [`apps/weightroom/design.md`](../apps/weightroom/design.md) (the
token deltas, §2, and the component list, §5); [ADR-0128](../../adr/0128-mirrorwall-vendors-htmx-and-applications-may-adopt-it.md).

**Work**

Gate A — tokens:
* `--mw-font-size-{base,sm,xs,title,figure}`, `--mw-sidebar-w`, `--mw-label-tracking`,
  `--mw-meter-h`, `--mw-row-h-comfortable` — additive, root-only, no existing rule reads them yet.
* `--mw-status-{ok,degraded,stopped,unknown}`, both themes, four new 3:1 contrast pairs (the dot
  carries the colour; its word is the page's ordinary text, so no new text-contrast obligation
  follows it).
* `--mw-row-h` keeps its 0.2.2 value; `table[data-density="dense"]` (`tables.css`) overrides it to
  32px scoped to the table that asks for it, which is what keeps every unmigrated page unchanged.
* `--mw-font-data` names `"JetBrains Mono"` first, vendored via two `@font-face` rules (Regular
  and Bold, SIL OFL 1.1) at the top of `tokens.css`, loaded by a path relative to the stylesheet.
* htmx 2.0.10 and htmx-ext-sse 2.2.2 vendored under `static/vendor/htmx/` (0BSD), pinned, combined
  19 075 bytes gzipped — under the ADR's 20 KB budget. `THIRD_PARTY_NOTICES.md` and
  `static/ASSETS.sha256` updated; the application-vocabulary scan exempts `static/vendor/` (naming
  is upstream's, not this package's) while every other vendoring rule — digest, licence — still
  applies to it.

Gate B — components (all in `templates/mirrorwall/components.html` unless noted):
* `status_dot(status="unknown", label=None)` — the dot-plus-word pattern, `data-status` driven.
* `app_tab(label, href, status=None, selected=False)` — a top-bar link to a peer application.
* `meter(label, value_text, percent=None)` — a `role="meter"` track/fill/value; with `percent`
  omitted (a measurement this machine cannot take, ADR-0016) it renders label and value only,
  never a bar claiming a number it does not have. `telemetry_bar(stream_url, meters=None)` gained
  the `meters` parameter to append these after the fixed CPU/RAM/GPU/VRAM fields.
* `card(label, value, note=None, kind="default")` — `kind="figure"` adds the 22px mono tabular
  value class; the default renders exactly as before.
* `table(..., density=None)` and a per-column `mono` flag alongside the existing `numeric` one —
  `density="dense"` sets `data-density="dense"` on the `<table>`, scoping the row-height override
  to it alone; `mono` reuses the existing `.mono` utility rather than inventing a second one.
* `log_pane(pane_id, stream_url=None, max_lines=500, label="Log")` plus `static/js/log_pane.js` —
  the bounded buffer, the *dropped N lines* frame and the pause button are the module's job
  (ADR-0128 rule 6); swaps are `hx-ext="sse"`/`sse-swap`/`hx-swap` attributes when `stream_url` is
  given, and the pane's initial, JavaScript-free state works with neither.
* `side_nav(sections, footer=None, label="Sections")` — a section's pages are keyed `links`, not
  `items` (a plain dict's `.items` resolves to the built-in method before Jinja's key-lookup
  fallback, so `section.items` would silently iterate `dict.items` the first time a caller passed
  a real dict).
* `base.html` loads htmx only when the caller's context sets `mirrorwall.htmx` true, probed with
  `is defined` throughout (safe under `StrictUndefined` whether or not `mirrorwall` is passed at
  all); the CSRF token goes out once through `hx-headers` on `<body>`.

**Files/subsystems**
```text
src/mirrorwall/static/css/{tokens,tables,components,layout}.css   (edited)
src/mirrorwall/static/css/tokens.json                             (edited, kept in sync)
src/mirrorwall/static/vendor/htmx/{htmx.min.js,htmx-ext-sse.js,LICENSE}
src/mirrorwall/static/fonts/jetbrains-mono/{JetBrainsMono-Regular.woff2,
                                             JetBrainsMono-Bold.woff2,LICENSE}
src/mirrorwall/static/js/log_pane.js
src/mirrorwall/templates/mirrorwall/{components,telemetry_bar,base}.html   (edited)
tests/unit/test_tokens.py                     (four new contrast pairs)
tests/snapshot/test_components.py             (every new macro, both themes)
tests/js/test_log_pane.py                     (Node DOM harness: bound, drop count, pause)
tests/test_no_application_vocabulary.py       (vendor exemption; new generic parameter names)
```

**Tests**
* Contrast: the four status tokens at 3:1 against `--mw-surface`, both themes.
* Snapshot: `status_dot`, `app_tab`, `meter` (with and without `percent`), `card(kind="figure")`,
  `table(density=..., mono columns)`, `log_pane` (with and without `stream_url`), `side_nav`; and,
  for every macro that changed shape, a test proving the pre-0.3 call renders unchanged.
* `log_pane.js`: lines beyond `max_lines` are trimmed and counted as dropped; a pane within budget
  is untouched; the pause button toggles `aria-pressed`/label; a paused pane sets
  `event.detail.shouldSwap = false` on `htmx:beforeSwap`; an unpaused one leaves it alone.
* Term scan: `static/vendor/` exempted; every new macro's required parameters are still generic
  presentation words (`href`, `pane_id`, `sections`, `value_text` added to the allowed set).
* Asset manifest: every new vendored file's digest recorded; every vendored file (now non-empty)
  named in `THIRD_PARTY_NOTICES.md` with its licence file present.

**Acceptance criteria**
1. Every existing snapshot test for an unchanged macro still passes unmodified — the upgrade is
   byte-identical for a page that does not opt into `kind`, `density`, `meters` or `mirrorwall.htmx`.
2. The four new status tokens and the vendored font and htmx files pass every existing vendoring,
   contrast and offline-asset test with no exemption beyond the one stated above.
3. `ruff format --check`, `ruff check`, `mypy --strict`, `lint-imports` clean; coverage 98.02 %
   (floor 95 %).

**Known risks:** a dict-keyed macro parameter shadowing a builtin method name (`section.items` vs
`dict.items`) — the failure mode `side_nav` avoided by naming the key `links` instead, documented
in the macro's own comment so it is not reintroduced.
**Likely failure modes:** a required macro parameter that reads as domain-specific rather than
presentational (`test_no_component_macro_has_an_application_shaped_required_parameter` catches
this at the macro-signature level, not just by review).
**Gold standards:** upgrade without page changes (proven per-macro, not just at the suite level);
accessible (`role="meter"`, the dot's word, the log pane's `role="log"`); offline (vendored, no
CDN); no application vocabulary (vendor exemption is scoped and documented, not a blanket carve-out).
**Deferred:** the four applications' own adoption of these tokens and components (row WM2); removing
the pre-htmx swap/SSE JS modules (ADR-0128 rule 7, not before every application has adopted htmx).
