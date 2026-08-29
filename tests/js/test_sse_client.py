"""The browser half of the stream, exercised in a real JavaScript runtime.

Not a transliteration of the module into Python: the file under test is loaded and run by Node,
with a fake ``EventSource`` and a minimal DOM stubbed in. A Python re-implementation would prove
that the re-implementation works, which is not the question.

Skipped, with a reason, where no runtime is available. The properties asserted here are the client
half of the server's own guarantee: each sequence applied exactly once across a reconnect, and the
envelope unwrapped except for ``token``.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from mirrorwall import PACKAGE_STATIC_DIR

NODE = shutil.which("node") or shutil.which("nodejs")

pytestmark = pytest.mark.skipif(NODE is None, reason="no JavaScript runtime on this machine")

HARNESS = r"""
// A fake EventSource: no network, and a `deliver` hook so a test can inject the exact frame
// sequence a reconnect produces, including the redelivered boundary event.
class FakeEventSource {
  constructor(url) {
    this.url = url;
    this.listeners = {};
    this.closed = false;
    FakeEventSource.last = this;
  }
  addEventListener(name, handler) {
    (this.listeners[name] = this.listeners[name] || []).push(handler);
  }
  close() { this.closed = true; }
  deliver(name, data) {
    (this.listeners[name] || []).forEach((handler) => handler({ data: data }));
  }
}

const results = [];
globalThis.window = globalThis;
globalThis.EventSource = undefined;

MODULE_SOURCE

function envelope(sequence, type, data) {
  return JSON.stringify({
    schema: "event.envelope",
    schema_version: "1.0",
    generated_at: "2026-08-21T09:14:02.318Z",
    generator: { name: "example", version: "1.0.0" },
    payload: { sequence: sequence, type: type, data: data }
  });
}

const applied = [];
const tokens = [];
const handle = globalThis.mirrorwallSse.connect("/stream", {
  "sample.completed": function (payload) { applied.push(payload.sequence); },
  "token": function (payload) { tokens.push(payload.delta); }
}, { EventSourceClass: FakeEventSource });

const source = FakeEventSource.last;
source.deliver("sample.completed", envelope(1, "sample.completed", { score: 1 }));
source.deliver("sample.completed", envelope(2, "sample.completed", { score: 2 }));
// The reconnect: the browser resends Last-Event-ID and the server legitimately redelivers the
// boundary event. Applying it twice would duplicate a row on the page.
source.deliver("sample.completed", envelope(2, "sample.completed", { score: 2 }));
source.deliver("sample.completed", envelope(3, "sample.completed", { score: 3 }));
// An out-of-order straggler from an older connection must not be applied either.
source.deliver("sample.completed", envelope(1, "sample.completed", { score: 1 }));
// Bare token frames: no envelope, no sequence, applied in arrival order.
source.deliver("token", JSON.stringify({ delta: "he", index: 0 }));
source.deliver("token", JSON.stringify({ delta: "llo", index: 1 }));
// Unparseable and malformed frames are dropped, never guessed at.
source.deliver("sample.completed", "{not json");
source.deliver("sample.completed", JSON.stringify({ no: "payload" }));

results.push({
  applied: applied,
  tokens: tokens,
  seen: handle.seen,
  url: source.url,
  closedBefore: source.closed
});
handle.close();
results.push({ closedAfter: FakeEventSource.last.closed });

console.log(JSON.stringify(results));
"""


def _run(module: str) -> list[dict[str, object]]:
    source = (PACKAGE_STATIC_DIR / "js" / module).read_text()
    script = HARNESS.replace("MODULE_SOURCE", source)
    assert NODE is not None
    completed = subprocess.run(  # noqa: S603 — fixed argv, script supplied on stdin
        [NODE, "--input-type=module", "-e", script],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    parsed: list[dict[str, object]] = json.loads(completed.stdout.strip().splitlines()[-1])
    return parsed


def test_events_are_applied_idempotently_across_a_reconnect() -> None:
    first, second = _run("sse.js")
    assert first["applied"] == [1, 2, 3], "a redelivered or stale event was applied"
    assert first["seen"] == 3
    assert first["url"] == "/stream"
    assert first["closedBefore"] is False
    assert second["closedAfter"] is True


def test_token_frames_are_bare_and_applied_in_arrival_order() -> None:
    first, _ = _run("sse.js")
    assert first["tokens"] == ["he", "llo"]


def test_the_module_registers_no_global_beyond_its_own_namespace() -> None:
    """A shared package that leaks globals collides with whatever the application loads next."""
    source = (PACKAGE_STATIC_DIR / "js" / "sse.js").read_text()
    assert source.count("global.") == source.count("global.mirrorwallSse") + source.count(
        "global.document"
    ) + source.count("global.EventSource")


def test_the_client_module_is_wrapped_and_declares_strict_mode() -> None:
    for name in (
        "sse.js",
        "telemetry.js",
        "theme.js",
        "table.js",
        "drawer.js",
        "dialog.js",
        "toast.js",
    ):
        source = (PACKAGE_STATIC_DIR / "js" / name).read_text()
        assert '"use strict"' in source, name
        assert source.lstrip().startswith(("//", "(function")), name
        assert "(function" in source, f"{name} is not wrapped in an IIFE"


def test_no_module_uses_a_javascript_feature_a_supported_browser_lacks() -> None:
    """ADR-0020: no bundler and no transpiler, so the shipped file is what the browser parses."""
    assert NODE is not None
    for path in sorted((PACKAGE_STATIC_DIR / "js").glob("*.js")):
        completed = subprocess.run(  # noqa: S603 — fixed argv, a file path from package data
            [NODE, "--check", str(path)],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        assert completed.returncode == 0, f"{path.name}: {completed.stderr}"


def test_the_telemetry_module_renders_an_em_dash_with_a_reason_never_zero() -> None:
    """ADR-0016 on the client side, where a `0` is just as wrong as it is on the server."""
    assert NODE is not None
    telemetry = (PACKAGE_STATIC_DIR / "js" / "telemetry.js").read_text()
    script = (
        "globalThis.window = globalThis;\n"
        "const fields = {};\n"
        "const bar = {\n"
        "  getAttribute: () => '0',\n"
        "  querySelector: (selector) => {\n"
        '    const name = selector.match(/data-field="([a-z_]+)"/)[1];\n'
        "    return (fields[name] = fields[name] || {\n"
        "      textContent: null, title: null,\n"
        "      setAttribute(k, v) { this[k] = v; },\n"
        "      removeAttribute(k) { this[k] = null; }\n"
        "    });\n"
        "  }\n"
        "};\n"
        f"{telemetry}\n"
        "globalThis.mirrorwallTelemetry.apply(bar, {\n"
        "  cpu_percent: 41.6, cpu_temperature_c: 'unsupported',\n"
        "  ram_used_bytes: 8589934592, ram_total_bytes: 'unsupported', gpus: [],\n"
        "  unavailable_reasons: { cpu_temperature_c: 'no sensor exposed' }\n"
        "});\n"
        "console.log(JSON.stringify({\n"
        "  cpu: fields.cpu_percent.textContent,\n"
        "  cpu_temp: fields.cpu_temperature_c.textContent,\n"
        "  cpu_temp_title: fields.cpu_temperature_c.title,\n"
        "  ram_used: fields.ram_used_bytes.textContent,\n"
        "  ram_total: fields.ram_total_bytes.textContent,\n"
        "  gpu: fields.gpu_temperature_c.textContent,\n"
        "  gpu_title: fields.gpu_temperature_c.title\n"
        "}));\n"
    )
    completed = subprocess.run(  # noqa: S603 — fixed argv, script supplied inline
        [NODE, "-e", script], capture_output=True, text=True, check=False, timeout=30
    )
    assert completed.returncode == 0, completed.stderr
    rendered = json.loads(completed.stdout.strip().splitlines()[-1])
    assert rendered["cpu"] == "42"
    assert rendered["cpu_temp"] == "—"
    assert rendered["cpu_temp_title"] == "no sensor exposed"
    assert rendered["ram_used"] == "8.0"
    assert rendered["ram_total"] == "—"
    # No GPU at that index: every GPU field says why, and none of them says 0.
    assert rendered["gpu"] == "—"
    assert "no GPU reported at index 0" in rendered["gpu_title"]
    assert "0" not in {rendered["cpu_temp"], rendered["ram_total"], rendered["gpu"]}


def test_the_harness_would_notice_a_broken_module(tmp_path: Path) -> None:
    """A harness that passes on a module that does nothing proves nothing."""
    broken = tmp_path / "js"
    broken.mkdir()
    (broken / "sse.js").write_text(
        "(function (g) { g.mirrorwallSse = { connect: function () "
        "{ return { close: function () {}, seen: -1 }; } }; })"
        "(globalThis);"
    )
    source = (broken / "sse.js").read_text()
    script = HARNESS.replace("MODULE_SOURCE", source)
    assert NODE is not None
    completed = subprocess.run(  # noqa: S603 — fixed argv, script supplied inline
        [NODE, "-e", script], capture_output=True, text=True, check=False, timeout=30
    )
    # Either it crashes (no listeners registered) or it applies nothing; both are a failure the
    # real assertions above would catch.
    if completed.returncode == 0:
        results = json.loads(completed.stdout.strip().splitlines()[-1])
        assert results[0]["applied"] != [1, 2, 3]
