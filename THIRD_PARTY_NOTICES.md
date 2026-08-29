# Third-party notices

MirrorWall serves its own assets from the installed package (spec §14: no CDN, no network request
at page load), so anything it ships must be recorded here with a licence and a checksum.

## Vendored runtime assets

**None as of 0.2.0.**

That is a design outcome, not an omission:

* **Charting library.** No third-party chart library is vendored. Every chart in the suite is
  inline SVG drawn from the caller's own figures, with each series coloured by a `--mw-chart-*`
  token — which is what lets the theme switch re-theme a chart without redrawing it, and what
  keeps `charts.css`'s accessible table alternative the same data rather than a parallel copy.
  A library would add a licence, a checksum to maintain, and a second colour system to reconcile
  with the tokens.
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
