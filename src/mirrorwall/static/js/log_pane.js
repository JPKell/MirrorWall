// mirrorwall/log_pane.js — the behaviour the design brief keeps out of HTML attributes.
//
// Swaps are htmx's job (`sse-swap="log"`, `hx-swap="beforeend"`); this module does only what
// ADR-0128 rule 6 leaves for a module: bound the buffer so a long-lived tail does not grow memory
// forever, and pause — both something no `hx-*` attribute expresses. The server already renders
// each appended line with the level colouring `components.css` reads from `data-level`; this file
// never invents or recolours a line's content.
//
// ADR-0020: a log pane with this file absent still shows its initial, server-rendered state.
(function () {
  "use strict";

  var LINE_SELECTOR = ".log-pane-line";

  function boundedBuffer(pane, body) {
    var maxLines = parseInt(pane.getAttribute("data-max-lines"), 10);
    if (!(maxLines > 0)) { return; }
    var dropped = 0;
    var droppedFrame = pane.querySelector("[data-log-pane-dropped]");
    var droppedCount = pane.querySelector("[data-log-pane-dropped-count]");

    function trim() {
      var lines = body.querySelectorAll(LINE_SELECTOR);
      var excess = lines.length - maxLines;
      if (excess <= 0) { return; }
      for (var index = 0; index < excess; index += 1) {
        lines[index].remove();
        dropped += 1;
      }
      if (droppedFrame && droppedCount) {
        droppedCount.textContent = String(dropped);
        droppedFrame.hidden = false;
      }
    }

    // A `MutationObserver`, not a per-swap hook, because htmx's `sse-swap` inserts nodes directly
    // — there is no per-line callback to attach trimming to.
    new MutationObserver(trim).observe(body, { childList: true });
  }

  function wirePause(pane) {
    var button = pane.querySelector("[data-log-pane-pause]");
    if (!button) { return; }
    button.addEventListener("click", function () {
      var paused = button.getAttribute("aria-pressed") === "true";
      button.setAttribute("aria-pressed", paused ? "false" : "true");
      button.textContent = paused ? "Pause" : "Resume";
    });
  }

  function wire(pane) {
    var body = pane.querySelector(".log-pane-body");
    if (!body) { return; }
    boundedBuffer(pane, body);
    wirePause(pane);
  }

  function wireAll() {
    document.querySelectorAll("[data-log-pane]").forEach(wire);
    // A paused pane still receives the SSE event; it just declines the swap, which is what keeps
    // the pause a display choice rather than a disconnect a reconnect would have to repair.
    document.body.addEventListener("htmx:beforeSwap", function (event) {
      var pane = event.target.closest("[data-log-pane]");
      if (!pane) { return; }
      var button = pane.querySelector("[data-log-pane-pause]");
      if (button && button.getAttribute("aria-pressed") === "true") {
        event.detail.shouldSwap = false;
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", wireAll);
  } else {
    wireAll();
  }
})();
