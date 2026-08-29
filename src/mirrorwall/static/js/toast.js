// mirrorwall/toast.js — transient status messages in a polite live region.
//
// `role="status"` with `aria-live="polite"` is on the region in the macro, not added here: a live
// region announced only after JavaScript inserted it is a region a screen reader never saw
// created, and the announcement is lost.
(function () {
  "use strict";

  var DEFAULT_TIMEOUT_MS = 6000;

  function region() {
    return document.getElementById("mw-toast-region");
  }

  function show(message, options) {
    var host = region();
    if (!host) { return null; }
    var settings = options || {};
    var toast = document.createElement("div");
    toast.className = "toast";
    toast.setAttribute("data-tone", settings.tone || "neutral");
    toast.textContent = message;
    host.appendChild(toast);
    var timeout = settings.timeoutMs === undefined ? DEFAULT_TIMEOUT_MS : settings.timeoutMs;
    if (timeout > 0) {
      window.setTimeout(function () {
        if (toast.parentNode) { toast.parentNode.removeChild(toast); }
      }, timeout);
    }
    return toast;
  }

  window.mirrorwallToast = { show: show };
})();
