# Third-party notices

MirrorWall serves its own assets from the installed package (spec §14: no CDN, no network request
at page load), so anything it ships must be recorded here with a licence and a checksum.

## Vendored runtime assets

### htmx 2.0.10

`static/vendor/htmx/htmx.min.js` — the core library. Licence: 0BSD (`static/vendor/htmx/LICENSE`).
Source: https://unpkg.com/htmx.org@2.0.10/dist/htmx.min.js

### htmx-ext-sse 2.2.2

`static/vendor/htmx/htmx-ext-sse.js` — the Server Sent Events extension, which every `sse-swap`
region in the design brief's components (`log_pane`, and any application page that opts into
htmx) depends on. Same licence and directory as htmx itself: `static/vendor/htmx/LICENSE`.
Source: https://unpkg.com/htmx-ext-sse@2.2.2/sse.js

Both files are vendored under ADR-0128 (`WeightRoom/docs/adr/0128-…`): pinned, served from this
package with the same content-hashed URL every asset gets, no CDN, no fetch at runtime. Combined
they are under 20 KB gzipped, the budget the ADR sets.

### ECharts 6.1.0

`static/vendor/echarts/echarts.min.js` — the full UMD build (every chart type, including the
heatmap a later WeightRoomGym row wants; the `common` build is ~400 KB smaller but has none).
Licence: Apache License 2.0 (`static/vendor/echarts/LICENSE`). Source:
https://cdn.jsdelivr.net/npm/echarts@6.1.0/dist/echarts.min.js

Vendored under ADR-0142 (`WeightRoom/docs/adr/0142-…`, superseding ADR-0139 for this one library
by name): pinned, served the same way as htmx, no CDN, no fetch at runtime, loaded only when a
page's context sets `mirrorwall.echarts` true (`chart_container()`'s `data-echarts`, `charts.js`).
1 121 883 bytes uncompressed (1.07 MiB), 367 915 bytes gzipped — 71.6 KiB over spec §15's
"Charting vendor ≤ 1 MB" row at the pinned version; the ADR carries the measurement and the
decision to keep the full build for the heatmap rather than trim to `common` and stay under it.

### JetBrains Mono 2.304 (via `@fontsource/jetbrains-mono` 5.2.5)

`static/fonts/jetbrains-mono/JetBrainsMono-Regular.woff2` and
`static/fonts/jetbrains-mono/JetBrainsMono-Bold.woff2` — the data font
`--mw-font-data` now names first (design brief §2), loaded through the two `@font-face` rules at
the top of `tokens.css` by a path relative to that stylesheet, so no application configuration
is needed to see it. Licence: SIL Open Font License 1.1
(`static/fonts/jetbrains-mono/LICENSE`). Source:
https://cdn.jsdelivr.net/npm/@fontsource/jetbrains-mono@5.2.5/files/

## Not vendored

That is a design outcome, not an omission:

* **Inter.** The font is *named first* in `--mw-font-ui` and is not shipped. The stack
  (`Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`)
  renders in Inter where the reader has it and in the platform UI face otherwise — a difference in
  letterforms, not in layout, because every measurement in the design system is in tokens rather
  than in ems of a specific face. Shipping ~400 KB of WOFF2 for that difference, on a local
  application whose reader already has a good UI font, was not the trade to make.
* **Icons.** `static/icons/sprite.svg` is original to this package: sixteen glyphs on a 24×24
  grid, stroked with `currentColor`. No third-party icon set is vendored, so none is licensed.

## Adding a vendored asset

The mechanism is in place and used by `tests/unit/test_assets.py`, which recomputes every digest
in `static/ASSETS.sha256` and fails on a mismatch. To add one:

1. Put the file under `src/mirrorwall/static/vendor/<name>/`.
2. Put its upstream licence beside it, verbatim, as `LICENSE`.
3. Add a section here: what it is, the exact upstream version, the licence, and the source URL.
4. Regenerate `static/ASSETS.sha256` (`python -m mirrorwall.tools.hash_assets`, or the one-line
   `sha256sum` equivalent the file's own header records).

A vendored file with no entry here fails the notices test; an entry whose digest does not match
the file fails the asset test. Neither is skippable.
