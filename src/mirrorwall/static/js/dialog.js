// mirrorwall/dialog.js — modal dialogs on the platform's own <dialog> element.
//
// The element already provides the modal semantics, the backdrop, the focus trap and Escape;
// this file only wires triggers to it, so there is no hand-rolled modal to get wrong.
(function () {
  "use strict";

  function wire() {
    Array.prototype.forEach.call(document.querySelectorAll("[data-dialog-open]"), function (trigger) {
      var dialog = document.getElementById(trigger.getAttribute("data-dialog-open"));
      if (!dialog || typeof dialog.showModal !== "function") { return; }
      trigger.addEventListener("click", function () { dialog.showModal(); });
    });
    Array.prototype.forEach.call(document.querySelectorAll("[data-dialog-close]"), function (button) {
      var dialog = button.closest("dialog");
      if (!dialog) { return; }
      button.addEventListener("click", function () { dialog.close(); });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", wire);
  } else {
    wire();
  }
})();
