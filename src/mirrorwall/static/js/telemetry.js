// mirrorwall/telemetry.js — live-updates the telemetry bar from a generic telemetry payload.
//
// The bar's fields start as em dashes in the template and this module replaces one only when a
// value was actually reported. `"unsupported"` is ADR-0016's wire form for a reading that does
// not exist in this environment, and it renders as an em dash with the producer's own reason in a
// tooltip — never as 0, which would be indistinguishable from a real measurement of nothing.
//
// The payload shape is deliberately generic: cpu/ram fields on the snapshot, an array of per-device
// GPU readings, and an `unavailable_reasons` map. Nothing here knows which application is running.
(function (global) {
  "use strict";

  var UNSUPPORTED = "unsupported";
  var EM_DASH = "—";
  var GB = 1024 * 1024 * 1024;

  function isAbsent(value) {
    return value === UNSUPPORTED || value === null || value === undefined;
  }

  function rounded(value) {
    return isAbsent(value) ? EM_DASH : String(Math.round(value));
  }

  function gigabytes(value) {
    return isAbsent(value) ? EM_DASH : (value / GB).toFixed(1);
  }

  function setField(bar, name, text, reason) {
    var element = bar.querySelector('[data-field="' + name + '"]');
    if (element === null) { return; }
    element.textContent = text;
    if (text === EM_DASH && reason) {
      element.title = reason;
      element.setAttribute("aria-label", "Unavailable: " + reason);
    } else {
      element.removeAttribute("title");
      element.removeAttribute("aria-label");
    }
  }

  function apply(bar, snapshot) {
    var reasons = snapshot.unavailable_reasons || {};
    setField(bar, "cpu_percent", rounded(snapshot.cpu_percent), reasons.cpu_percent);
    setField(bar, "cpu_temperature_c", rounded(snapshot.cpu_temperature_c), reasons.cpu_temperature_c);
    setField(bar, "ram_used_bytes", gigabytes(snapshot.ram_used_bytes), reasons.ram_used_bytes);
    setField(bar, "ram_total_bytes", gigabytes(snapshot.ram_total_bytes), reasons.ram_total_bytes);

    var gpus = snapshot.gpus || [];
    var index = Number(bar.getAttribute("data-gpu-index") || 0);
    var gpu = gpus.length > index ? gpus[index] : null;
    if (gpu === null) {
      // No device at this index is not a device reading zero: every GPU field says why instead.
      var why = reasons.gpu || "no GPU reported at index " + index;
      ["gpu_utilization_percent", "gpu_temperature_c", "gpu_power_watts",
       "gpu_vram_used_bytes", "gpu_vram_total_bytes"].forEach(function (name) {
        setField(bar, name, EM_DASH, why);
      });
      return;
    }
    setField(bar, "gpu_utilization_percent", rounded(gpu.utilization_percent));
    setField(bar, "gpu_temperature_c", rounded(gpu.temperature_c));
    setField(bar, "gpu_power_watts", rounded(gpu.power_watts));
    setField(bar, "gpu_vram_used_bytes", gigabytes(gpu.vram_used_bytes));
    setField(bar, "gpu_vram_total_bytes", gigabytes(gpu.vram_total_bytes));
  }

  function wire() {
    var bar = global.document && global.document.getElementById("mw-telemetry-bar");
    if (!bar) { return null; }
    var url = bar.getAttribute("data-telemetry-url");
    if (!url || !global.mirrorwallSse) { return null; }
    return global.mirrorwallSse.connect(url, {
      "telemetry.sampled": function (payload) { apply(bar, payload.data || payload); }
    });
  }

  global.mirrorwallTelemetry = { apply: apply, wire: wire };

  if (global.document) {
    if (global.document.readyState === "loading") {
      global.document.addEventListener("DOMContentLoaded", wire);
    } else {
      wire();
    }
  }
})(typeof window === "undefined" ? globalThis : window);
