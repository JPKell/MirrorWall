// mirrorwall/charts.js — ECharts initialiser: reads `data-echarts`, redraws on theme change.
//
// ADR-0142: ECharts is vendored and opt-in per page (`mirrorwall.echarts`, the htmx precedent of
// ADR-0128). The option is the caller's JSON, parsed off `chart_container()`'s `.chart-surface`
// element; colour is never baked into it, because ECharts draws to a canvas that a CSS variable
// cannot repaint — this file supplies the palette, background and text colour read fresh from the
// tokens at every draw, which is what lets `theme.js`'s `mirrorwall:themechange` redraw a chart
// correctly instead of leaving it in the theme it was born in.
//
// ADR-0020 rule 5: the caller's own accessible content (a table, an SVG) is `chart_container()`'s
// `caller()` body, rendered whether or not this file — or ECharts, or a `data-echarts` value that
// fails to parse — ever runs. This module only ever adds a drawing on top.
(function () {
  "use strict";

  var SELECTOR = "[data-echarts]";
  var charts = []; // {instance, option} for every element wired on this page

  function tokenColour(style, name) {
    return style.getPropertyValue(name).trim();
  }

  // ponytail: axis line/label colour is ECharts' own default in both themes, not token-matched —
  // upgrade to per-axis theming if a reviewer flags contrast on the axis rule itself.
  function themedOption(option) {
    var style = getComputedStyle(document.documentElement);
    var palette = [1, 2, 3, 4, 5, 6].map(function (n) {
      return tokenColour(style, "--mw-chart-" + n);
    });
    return Object.assign(
      {
        color: palette,
        backgroundColor: "transparent",
        textStyle: { color: tokenColour(style, "--mw-text-muted"), fontSize: 11 },
      },
      option
    );
  }

  function draw(entry) {
    entry.instance.setOption(themedOption(entry.option), true);
  }

  function wire(el) {
    var raw = el.getAttribute("data-echarts");
    if (!raw || typeof window.echarts === "undefined") { return; }
    var option;
    try {
      option = JSON.parse(raw);
    } catch (error) {
      return; // malformed option: the caller's own accessible content is the whole page
    }
    var entry = { instance: window.echarts.init(el), option: option };
    charts.push(entry);
    draw(entry);
  }

  function wireAll() {
    document.querySelectorAll(SELECTOR).forEach(wire);
  }

  document.addEventListener("mirrorwall:themechange", function () {
    charts.forEach(draw);
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", wireAll);
  } else {
    wireAll();
  }
})();
