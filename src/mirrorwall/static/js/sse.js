// mirrorwall/sse.js — the browser side of the stream.
//
// A thin, testable wrapper over the platform's own EventSource. The browser already reconnects on
// a dropped connection and already resends Last-Event-ID from the last `id:` it saw, so none of
// that is reimplemented here; what this module adds is the part the platform does not do:
//
//   * **Idempotent application.** A reconnect can legitimately redeliver the boundary event, and
//     a server bug can redeliver more. Handlers here see each sequence exactly once, so a page
//     that appends a row does not append it twice — the client half of the same guarantee the
//     server makes at the replay/live handoff.
//   * **Envelope unwrapping**, with the one documented exception: every frame carries the SetSpec
//     event envelope and is delivered as its `payload`, except `token`, which is bare
//     (ADR-0025 §3).
//
// ADR-0020: nothing on the page depends on this file. Without it the page is complete and static.
(function (global) {
  "use strict";

  var TOKEN_EVENT = "token";

  function parseFrame(eventName, raw) {
    var parsed;
    try {
      parsed = JSON.parse(raw);
    } catch (error) {
      return null; // a frame we cannot parse is dropped, never guessed at
    }
    if (eventName === TOKEN_EVENT) {
      return { sequence: null, payload: parsed };
    }
    if (!parsed || typeof parsed !== "object" || !parsed.payload) {
      return null;
    }
    var sequence = parsed.payload.sequence;
    return {
      sequence: typeof sequence === "number" ? sequence : null,
      payload: parsed.payload,
      envelope: parsed
    };
  }

  // Connect to `url` and dispatch each event to `handlers[eventName]`.
  //
  // Returns a handle with `close()` and `seen` (the highest sequence applied), so a test can
  // assert idempotence without reaching into the module.
  function connect(url, handlers, options) {
    var settings = options || {};
    var Source = settings.EventSourceClass || global.EventSource;
    if (typeof Source !== "function") { return null; }

    var source = new Source(url);
    var highest = typeof settings.after === "number" ? settings.after : -1;

    function apply(eventName, event) {
      var frame = parseFrame(eventName, event.data);
      if (frame === null) { return; }
      // The one place duplicates are stopped on this side. A bare token frame carries no
      // sequence, so it is applied unconditionally: tokens are appended in arrival order and a
      // redelivered one would be a server bug this module cannot detect.
      if (frame.sequence !== null) {
        if (frame.sequence <= highest) { return; }
        highest = frame.sequence;
      }
      var handler = handlers[eventName];
      if (typeof handler === "function") { handler(frame.payload, frame.envelope || null); }
    }

    Object.keys(handlers).forEach(function (eventName) {
      source.addEventListener(eventName, function (event) { apply(eventName, event); });
    });

    return {
      close: function () { source.close(); },
      get seen() { return highest; },
      source: source
    };
  }

  global.mirrorwallSse = { connect: connect, parseFrame: parseFrame, TOKEN_EVENT: TOKEN_EVENT };
})(typeof window === "undefined" ? globalThis : window);
