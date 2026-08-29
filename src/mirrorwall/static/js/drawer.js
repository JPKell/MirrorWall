// mirrorwall/drawer.js — opening, closing and focus-trapping the drawer component.
//
// Progressive enhancement (ADR-0020): the drawer's content is in the page already. Without this
// file it renders as an ordinary aside; with it, a trigger toggles it, Escape closes it, and
// focus returns to whatever opened it.
(function () {
  "use strict";

  var lastTrigger = null;

  function focusable(root) {
    return root.querySelectorAll(
      'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]),' +
      ' textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
    );
  }

  function close(drawer) {
    drawer.hidden = true;
    if (lastTrigger) { lastTrigger.focus(); lastTrigger = null; }
  }

  function open(drawer, trigger) {
    lastTrigger = trigger || null;
    drawer.hidden = false;
    var targets = focusable(drawer);
    if (targets.length) { targets[0].focus(); }
  }

  function trap(drawer, event) {
    if (event.key === "Escape") { close(drawer); return; }
    if (event.key !== "Tab") { return; }
    var targets = focusable(drawer);
    if (!targets.length) { return; }
    var first = targets[0];
    var last = targets[targets.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      last.focus();
      event.preventDefault();
    } else if (!event.shiftKey && document.activeElement === last) {
      first.focus();
      event.preventDefault();
    }
  }

  function wire() {
    Array.prototype.forEach.call(document.querySelectorAll("[data-drawer-open]"), function (trigger) {
      var drawer = document.getElementById(trigger.getAttribute("data-drawer-open"));
      if (!drawer) { return; }
      trigger.addEventListener("click", function () { open(drawer, trigger); });
    });
    Array.prototype.forEach.call(document.querySelectorAll(".drawer"), function (drawer) {
      drawer.addEventListener("keydown", function (event) { trap(drawer, event); });
      Array.prototype.forEach.call(drawer.querySelectorAll("[data-drawer-close]"), function (button) {
        button.addEventListener("click", function () { close(drawer); });
      });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", wire);
  } else {
    wire();
  }
})();
