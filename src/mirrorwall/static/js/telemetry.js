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

  function ratio(used, total) {
    // A percentage needs both halves and a total that can actually divide: a machine that did not
    // report its RAM total has no bar, rather than a bar drawn against a guessed denominator.
    if (isAbsent(used) || isAbsent(total) || !(total > 0)) { return null; }
    return Math.max(0, Math.min(100, (used / total) * 100));
  }

  function setMeter(bar, name, percent) {
    var fill = bar.querySelector('[data-meter="' + name + '"]');
    if (fill === null) { return; }
    var track = fill.parentNode;
    if (percent === null) {
      // An empty track, not a zero-width bar claiming a measurement of nothing (ADR-0016).
      fill.style.width = "0";
      fill.removeAttribute("data-band");
      track.removeAttribute("role");
      track.removeAttribute("aria-valuenow");
      return;
    }
    var rounded_percent = Math.round(percent);
    fill.style.width = rounded_percent + "%";
    if (rounded_percent >= 90) { fill.setAttribute("data-band", "warn"); }
    else { fill.removeAttribute("data-band"); }
    track.setAttribute("role", "meter");
    track.setAttribute("aria-label", name);
    track.setAttribute("aria-valuemin", "0");
    track.setAttribute("aria-valuemax", "100");
    track.setAttribute("aria-valuenow", String(rounded_percent));
  }

  function apply(bar, snapshot) {
    var reasons = snapshot.unavailable_reasons || {};
    setField(bar, "cpu_percent", rounded(snapshot.cpu_percent), reasons.cpu_percent);
    setField(bar, "cpu_temperature_c", rounded(snapshot.cpu_temperature_c), reasons.cpu_temperature_c);
    setField(bar, "ram_used_bytes", gigabytes(snapshot.ram_used_bytes), reasons.ram_used_bytes);
    setField(bar, "ram_total_bytes", gigabytes(snapshot.ram_total_bytes), reasons.ram_total_bytes);
    setMeter(bar, "cpu", isAbsent(snapshot.cpu_percent) ? null : snapshot.cpu_percent);
    setMeter(bar, "ram", ratio(snapshot.ram_used_bytes, snapshot.ram_total_bytes));

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
      setMeter(bar, "gpu", null);
      setMeter(bar, "vram", null);
      return;
    }
    setField(bar, "gpu_utilization_percent", rounded(gpu.utilization_percent));
    setField(bar, "gpu_temperature_c", rounded(gpu.temperature_c));
    setField(bar, "gpu_power_watts", rounded(gpu.power_watts));
    setField(bar, "gpu_vram_used_bytes", gigabytes(gpu.vram_used_bytes));
    setField(bar, "gpu_vram_total_bytes", gigabytes(gpu.vram_total_bytes));
    setMeter(bar, "gpu", isAbsent(gpu.utilization_percent) ? null : gpu.utilization_percent);
    setMeter(bar, "vram", ratio(gpu.vram_used_bytes, gpu.vram_total_bytes));
  }

  var handle = null;

  // Connect the bar to its stream, once. Returns the open handle, or null with no bar, no URL or
  // no SSE client. Called again while connected it returns the same handle: a toggle pressed twice
  // never stacks a second EventSource.
  function wire() {
    if (handle !== null) { return handle; }
    var bar = global.document && global.document.getElementById("mw-telemetry-bar");
    if (!bar) { return null; }
    var url = bar.getAttribute("data-telemetry-url");
    if (!url || !global.mirrorwallSse) { return null; }
    handle = global.mirrorwallSse.connect(url, {
      "telemetry.sampled": function (payload) {
        var snapshot = payload.data || payload;
        apply(bar, snapshot);
        // Re-dispatched on the bar so an application's own fields can read the same frame instead
        // of opening a second EventSource to the same stream.
        bar.dispatchEvent(new CustomEvent("mw:telemetry", { detail: snapshot }));
      }
    });
    return handle;
  }

  // Close the stream. A hidden bar has no use for frames, and a server that polls per subscriber
  // has no reason to keep polling for it.
  function unwire() {
    if (handle !== null) {
      handle.close();
      handle = null;
    }
  }

  // Auto-connect only a bar that is rendered: an application may hide it before first paint (a
  // remembered preference), and a bar nobody can see must not open a stream.
  function autoWire() {
    var bar = global.document.getElementById("mw-telemetry-bar");
    if (bar && bar.getClientRects().length > 0) { wire(); }
  }

  global.mirrorwallTelemetry = { apply: apply, wire: wire, unwire: unwire };

  if (global.document) {
    if (global.document.readyState === "loading") {
      global.document.addEventListener("DOMContentLoaded", autoWire);
    } else {
      autoWire();
    }
  }
})(typeof window === "undefined" ? globalThis : window);
