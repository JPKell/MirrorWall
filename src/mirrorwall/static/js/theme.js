// mirrorwall/theme.js — the theme selector, and the hook that re-themes charts with it.
//
// The pre-paint bootstrap lives inline in base.html because it must run before first paint. This
// file handles the switch itself: applying a choice without a page reload, persisting it, and
// telling anything drawing with token colours to redraw (UI standards §9).
//
// ADR-0020: the page is complete before this file loads. Without it the reader keeps their system
// theme and every page still works.
(function () {
  "use strict";

  var DEFAULT_KEY = "mirrorwall-theme";

  function storageKey(select) {
    return select.getAttribute("data-theme-storage-key") || DEFAULT_KEY;
  }

  function read(key) {
    try {
      return window.localStorage.getItem(key);
    } catch (error) {
      return null; // private mode: the system theme is a correct answer
    }
  }

  function write(key, choice) {
    try {
      if (choice === "system") { window.localStorage.removeItem(key); }
      else { window.localStorage.setItem(key, choice); }
    } catch (error) { /* the choice still applies for this page view */ }
  }

  function apply(choice) {
    if (choice === "system") {
      document.documentElement.removeAttribute("data-theme");
    } else {
      document.documentElement.setAttribute("data-theme", choice);
    }
    // Charts draw with token colours read at draw time, so they redraw rather than restyle.
    document.dispatchEvent(new CustomEvent("mirrorwall:themechange", { detail: { theme: choice } }));
  }

  function wire() {
    var select = document.querySelector("[data-theme-select]");
    if (!select) { return; }
    var key = storageKey(select);
    var stored = read(key);
    select.value = stored === "light" || stored === "dark" ? stored : "system";
    select.addEventListener("change", function () {
      apply(select.value);
      write(key, select.value);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", wire);
  } else {
    wire();
  }
})();
