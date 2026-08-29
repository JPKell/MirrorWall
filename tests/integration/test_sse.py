"""The SSE stream, property by property.

Every bullet the development plan lists for this module is a test here, and each one is written
against the property rather than the implementation: ordered delivery, a gap-free and
duplicate-free replay/live handoff, heartbeats, bounded queues that drop, a terminal frame on
source failure, a clean close on disconnect, the frame shapes, the thread dispatch, and the
memory budget at 200 subscribers.
"""

from __future__ import annotations

import json
import re
import threading
import time
import tracemalloc
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any

import anyio
import pytest
import setspec
from setspec import GeneratorInfo, SchemaVersion
from starlette.responses import StreamingResponse

from mirrorwall.sse import (
    TOKEN_EVENT,
    Event,
    EventBroker,
    Subscription,
    format_frame,
    parse_last_event_id,
    sse_response,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

GENERATOR = GeneratorInfo(name="example", version="1.0.0")


class RecordingSource:
    """An in-memory EventSource: a persisted log plus this package's own broker.

    Exactly the shape an application has — a table it can `SELECT ... WHERE sequence > ?` from,
    and a fan-out its workers publish into — with the database replaced by a list so the tests
    can inject races the database would make hard to arrange.
    """

    def __init__(self, *, queue_size: int = 8) -> None:
        self.log: list[Event] = []
        self.broker = EventBroker(queue_size=queue_size)
        self.replay_calls: list[tuple[int, int]] = []
        self.replay_delay_seconds = 0.0
        self.fail_replay_after: int | None = None
        self.on_replay: Any = None
        self.after_replay: Any = None
        self.subscribe_enters = 0
        self.subscribe_exits = 0
        self._lock = threading.Lock()

    def append(self, event: Event) -> None:
        """Persist, then publish — the order an application must use."""
        with self._lock:
            self.log.append(event)
        self.broker.publish("s", event)

    def replay(self, *, stream_id: str, after_sequence: int, limit: int) -> Sequence[Event]:
        self.replay_calls.append((after_sequence, limit))
        if self.replay_delay_seconds:
            time.sleep(self.replay_delay_seconds)
        if self.fail_replay_after is not None and len(self.replay_calls) > self.fail_replay_after:
            message = "the database went away"
            raise RuntimeError(message)
        # Two hooks, at the two instants a handoff bug can hide in: `on_replay` fires *before* the
        # rows are selected, so an event it appends is in both the batch and the live queue (the
        # duplicate window); `after_replay` fires *after*, so an event it appends is in neither
        # the batch nor any subscription a replay-then-subscribe implementation opens later (the
        # gap window).
        if self.on_replay is not None:
            self.on_replay(after_sequence)
        with self._lock:
            rows = [event for event in self.log if event.sequence > after_sequence][:limit]
        if self.after_replay is not None:
            self.after_replay(after_sequence)
        return rows

    def subscribe(self, *, stream_id: str) -> _Subscribed:
        return _Subscribed(self, stream_id)


class _Subscribed:
    """A deliberately non-generator context manager, so only an explicit call can exit it.

    A `@contextmanager` generator's `finally` also runs when CPython collects it, which makes a
    "the subscription was released" assertion pass even for an implementation that never calls
    `__exit__` at all. This class has no such second path: `exits` counts explicit exits only.
    """

    def __init__(self, source: RecordingSource, stream_id: str) -> None:
        self._source = source
        self._inner = source.broker.subscribe(stream_id=stream_id)

    def __enter__(self) -> Subscription:
        self._source.subscribe_enters += 1
        return self._inner.__enter__()

    def __exit__(self, *exc: Any) -> None:
        self._source.subscribe_exits += 1
        self._inner.__exit__(*exc)


def _event(sequence: int, kind: str = "sample.completed", **data: Any) -> Event:
    return Event(
        sequence=sequence,
        type=kind,
        payload={"event_id": f"01J{sequence:022d}", "data": data},
    )


def _body_iterator(response: StreamingResponse) -> AsyncGenerator[str | bytes, None]:
    """The response's frame generator, typed as the async generator it actually is.

    ``StreamingResponse.body_iterator`` is declared as a bare ``AsyncIterable``; the object this
    module always puts there is an async generator, and the tests need ``aclose`` to prove the
    disconnect path.
    """
    iterator = response.body_iterator
    assert isinstance(iterator, AsyncGenerator)
    return iterator


def _text(chunk: str | bytes) -> str:
    return chunk if isinstance(chunk, str) else bytes(chunk).decode()


async def _collect(
    response: StreamingResponse, *, stop_after: int, timeout: float = 5.0
) -> list[str]:
    """Read frames until ``stop_after`` non-heartbeat frames have arrived, then close cleanly."""
    frames: list[str] = []
    body = _body_iterator(response)
    deadline = time.monotonic() + timeout
    try:
        async for chunk in body:
            frames.append(_text(chunk))
            if len([f for f in frames if f.startswith("id:")]) >= stop_after:
                break
            if time.monotonic() > deadline:  # pragma: no cover — a hung stream fails loudly
                pytest.fail(f"stream produced only {frames} before the timeout")
    finally:
        await body.aclose()
    return frames


def _sequences(frames: list[str]) -> list[int]:
    return [int(m.group(1)) for f in frames for m in [re.match(r"id: (\d+)", f)] if m]


async def _drain(
    response: StreamingResponse, *, until: int, settle: float = 0.3, timeout: float = 5.0
) -> list[int]:
    """Read until sequence ``until`` arrives, then keep reading briefly to catch a duplicate.

    Stopping at the first N frames is how a duplicate test passes without ever observing the
    duplicate; the settle window is what makes the assertion real.
    """
    body = _body_iterator(response)
    seen: list[int] = []
    try:
        with anyio.move_on_after(timeout):
            async for chunk in body:
                match = re.match(r"id: (\d+)", _text(chunk))
                if match:
                    seen.append(int(match.group(1)))
                if until in seen:
                    break
        with anyio.move_on_after(settle):
            async for chunk in body:
                match = re.match(r"id: (\d+)", _text(chunk))
                if match:
                    seen.append(int(match.group(1)))
    finally:
        await body.aclose()
    return seen


# --- frame shapes ------------------------------------------------------------------------


def test_every_non_token_frame_parses_through_load_envelope() -> None:
    frame = format_frame(_event(7, "sample.completed", score=0.75), generator=GENERATOR)
    assert frame.startswith("id: 7\nevent: sample.completed\ndata: ")
    assert frame.endswith("\n\n")
    data = frame.split("data: ", 1)[1].strip()
    envelope = setspec.load_envelope(data, expect="event.envelope", supported=[SchemaVersion(1, 0)])
    assert envelope.payload["sequence"] == 7
    assert envelope.payload["type"] == "sample.completed"
    assert envelope.payload["data"] == {"score": 0.75}
    assert envelope.generator.name == "example"


def test_the_token_frame_is_bare_and_is_the_only_exception() -> None:
    """ADR-0025 §3: one documented exception, and it applies only to `token`."""
    frame = format_frame(
        Event(sequence=3, type=TOKEN_EVENT, payload={"delta": "hi", "index": 0}),
        generator=GENERATOR,
    )
    data = frame.split("data: ", 1)[1].strip()
    assert json.loads(data) == {"delta": "hi", "index": 0}
    with pytest.raises(setspec.ValidationError):
        setspec.load_envelope(data, expect="event.envelope", supported=[SchemaVersion(1, 0)])

    # Every neighbouring event name is still enveloped.
    for name in ("tokens", "token.completed", "result", "error"):
        neighbour = format_frame(Event(sequence=4, type=name), generator=GENERATOR)
        payload = neighbour.split("data: ", 1)[1].strip()
        assert setspec.load_envelope(
            payload, expect="event.envelope", supported=[SchemaVersion(1, 0)]
        )


def test_the_frames_id_and_the_payloads_sequence_cannot_disagree() -> None:
    """The payload's own `sequence` is written here, not trusted from the caller."""
    frame = format_frame(
        Event(sequence=9, type="x", payload={"sequence": 1, "type": "wrong"}), generator=GENERATOR
    )
    envelope = setspec.load_envelope(
        frame.split("data: ", 1)[1].strip(),
        expect="event.envelope",
        supported=[SchemaVersion(1, 0)],
    )
    assert frame.startswith("id: 9\n")
    assert envelope.payload["sequence"] == 9
    assert envelope.payload["type"] == "x"


@pytest.mark.parametrize(
    ("header", "expected"),
    [(None, 0), ("", 0), ("41", 41), (" 41 ", 41), ("not-a-number", 0), ("-5", 0), ("\n\n", 0)],
)
def test_last_event_id_is_never_trusted_to_be_a_number(header: str | None, expected: int) -> None:
    assert parse_last_event_id(header) == expected


# --- the subscription --------------------------------------------------------------------


def test_a_full_subscription_drops_the_oldest_and_counts_it() -> None:
    subscription = Subscription(maxlen=3)
    for sequence in range(1, 6):
        subscription.publish(_event(sequence))
    assert subscription.dropped == 2
    assert [subscription.poll().sequence for _ in range(3)] == [3, 4, 5]  # type: ignore[union-attr]  # exactly three were queued
    assert subscription.poll() is None


def test_publishing_never_blocks_a_worker_thread_on_a_full_queue() -> None:
    subscription = Subscription(maxlen=1)
    started = time.monotonic()
    for sequence in range(10_000):
        subscription.publish(_event(sequence))
    assert time.monotonic() - started < 1.0


def test_a_closed_subscription_accepts_nothing_further() -> None:
    subscription = Subscription(maxlen=4)
    subscription.publish(_event(1))
    subscription.close()
    subscription.publish(_event(2))
    assert subscription.poll() is None
    assert subscription.closed is True


def test_a_subscription_must_be_able_to_hold_something() -> None:
    with pytest.raises(ValueError, match="at least 1"):
        Subscription(maxlen=0)


def test_the_broker_unregisters_on_exit_even_when_the_body_raises() -> None:
    broker = EventBroker()
    with pytest.raises(RuntimeError), broker.subscribe(stream_id="s"):
        assert broker.subscriber_count("s") == 1
        raise RuntimeError
    assert broker.subscriber_count("s") == 0


def test_the_broker_fans_out_to_every_current_subscriber() -> None:
    broker = EventBroker()
    with broker.subscribe(stream_id="s") as one, broker.subscribe(stream_id="s") as two:
        broker.publish("s", _event(1))
        broker.publish("other", _event(2))
        assert one.poll() is not None
        assert two.poll() is not None
        assert one.poll() is None


# --- the stream --------------------------------------------------------------------------


@pytest.mark.anyio
async def test_events_arrive_in_order_from_the_start_of_the_stream() -> None:
    source = RecordingSource()
    for sequence in range(1, 4):
        source.append(_event(sequence))
    response = sse_response(
        source, stream_id="s", last_event_id=None, generator=GENERATOR, poll_interval_seconds=0.01
    )
    frames = await _collect(response, stop_after=3)
    assert _sequences(frames) == [1, 2, 3]


@pytest.mark.anyio
async def test_replay_resumes_after_last_event_id_without_repeating_it() -> None:
    source = RecordingSource()
    for sequence in range(1, 6):
        source.append(_event(sequence))
    response = sse_response(
        source, stream_id="s", last_event_id="3", generator=GENERATOR, poll_interval_seconds=0.01
    )
    frames = await _collect(response, stop_after=2)
    assert _sequences(frames) == [4, 5]


@pytest.mark.anyio
async def test_the_replay_to_live_handoff_has_no_gap_and_no_duplicate() -> None:
    """The property this module exists for, with both races injected rather than hoped for.

    Two events are produced during the replay call, at the two instants that matter:

    * **4**, before the batch is selected: it is therefore in the replay batch *and* in the live
      queue. An implementation that forwards the live queue without deduping by sequence sends it
      twice, and the settle window in :func:`_drain` sees the second copy.
    * **5**, after the batch is selected: no replay will ever return it. An implementation that
      replays before subscribing has no subscription open at that instant, loses the event
      permanently, and this test times out waiting for it.

    Both mutations were applied to :mod:`mirrorwall.sse` and confirmed to fail here before this
    test was considered finished.
    """
    source = RecordingSource(queue_size=64)
    for sequence in range(1, 4):
        source.append(_event(sequence))

    def inject_before(_after: int) -> None:
        if len(source.replay_calls) == 1:
            source.append(_event(4))

    def inject_after(_after: int) -> None:
        if len(source.replay_calls) == 1:
            source.append(_event(5))

    source.on_replay = inject_before
    source.after_replay = inject_after
    response = sse_response(
        source, stream_id="s", last_event_id=None, generator=GENERATOR, poll_interval_seconds=0.01
    )
    seen = await _drain(response, until=5)
    assert seen == [1, 2, 3, 4, 5], seen
    assert len(seen) == len(set(seen)), f"an event was delivered twice: {seen}"


@pytest.mark.anyio
async def test_replay_reads_in_bounded_batches_not_one_round_trip_per_event() -> None:
    source = RecordingSource(queue_size=512)
    for sequence in range(1, 26):
        source.append(_event(sequence))
    response = sse_response(
        source,
        stream_id="s",
        last_event_id=None,
        generator=GENERATOR,
        replay_batch_size=10,
        poll_interval_seconds=0.01,
    )
    frames = await _collect(response, stop_after=25)
    assert _sequences(frames) == list(range(1, 26))
    # 25 events at 10 per batch: three full-or-short batches, not 25 round trips.
    assert len(source.replay_calls) <= 4, source.replay_calls
    assert all(limit == 10 for _, limit in source.replay_calls)


@pytest.mark.anyio
async def test_a_heartbeat_is_written_at_the_configured_cadence() -> None:
    source = RecordingSource()
    response = sse_response(
        source,
        stream_id="s",
        last_event_id=None,
        generator=GENERATOR,
        heartbeat_seconds=0.05,
        poll_interval_seconds=0.01,
    )
    body = _body_iterator(response)
    beats = 0
    try:
        with anyio.move_on_after(1.0):
            async for chunk in body:
                if _text(chunk).startswith(":"):
                    beats += 1
                if beats >= 3:
                    break
    finally:
        await body.aclose()
    assert beats >= 3


@pytest.mark.anyio
async def test_a_source_failure_ends_the_stream_with_one_terminal_frame() -> None:
    source = RecordingSource()
    source.append(_event(1))
    source.fail_replay_after = 1
    response = sse_response(
        source,
        stream_id="s",
        last_event_id=None,
        generator=GENERATOR,
        replay_batch_size=1,
        poll_interval_seconds=0.01,
    )
    body = _body_iterator(response)
    frames = [_text(chunk) async for chunk in body]
    terminal = frames[-1]
    assert "event: error" in terminal
    envelope = setspec.load_envelope(
        terminal.split("data: ", 1)[1].strip(),
        expect="event.envelope",
        supported=[SchemaVersion(1, 0)],
    )
    assert envelope.payload["code"] == "STREAM_FAILED"
    assert "the database went away" in envelope.payload["message"]


@pytest.mark.anyio
async def test_a_disconnect_releases_the_subscription() -> None:
    """A leaked slot per dropped connection is how a long-running server dies quietly."""
    source = RecordingSource()
    response = sse_response(
        source, stream_id="s", last_event_id=None, generator=GENERATOR, poll_interval_seconds=0.01
    )
    body = _body_iterator(response)
    source.append(_event(1))
    async for _ in body:
        break
    assert source.subscribe_enters == 1
    assert source.broker.subscriber_count("s") == 1
    await body.aclose()
    assert source.subscribe_exits == 1, "the subscription context manager was never exited"
    assert source.broker.subscriber_count("s") == 0


@pytest.mark.anyio
async def test_a_slow_source_does_not_block_the_event_loop() -> None:
    """ADR-0003 §7: the test that keeps the async edge honest.

    A 200 ms `replay` runs in a worker thread, so a probe measuring event-loop lag alongside it
    sees the loop still turning. If the dispatch were removed, the probe's own sleeps would be
    delayed by the full 200 ms and this fails.
    """
    source = RecordingSource()
    source.append(_event(1))
    source.replay_delay_seconds = 0.2

    worst_lag = 0.0

    async def probe() -> None:
        nonlocal worst_lag
        for _ in range(40):
            before = time.monotonic()
            await anyio.sleep(0.005)
            worst_lag = max(worst_lag, time.monotonic() - before - 0.005)

    response = sse_response(
        source, stream_id="s", last_event_id=None, generator=GENERATOR, poll_interval_seconds=0.01
    )
    body = _body_iterator(response)

    async def consume() -> None:
        async for _ in body:
            break

    async with anyio.create_task_group() as group:
        group.start_soon(probe)
        group.start_soon(consume)
    await body.aclose()

    assert worst_lag < 0.1, f"the event loop was blocked for {worst_lag * 1000:.0f} ms"


@pytest.mark.anyio
async def test_two_hundred_idle_subscribers_stay_within_the_memory_budget() -> None:
    """Acceptance criterion 3, measured rather than asserted."""
    broker = EventBroker(queue_size=256)
    tracemalloc.start()
    baseline = tracemalloc.take_snapshot()
    from contextlib import ExitStack

    with ExitStack() as stack:
        for index in range(200):
            stack.enter_context(broker.subscribe(stream_id=f"stream-{index}"))
        assert sum(broker.subscriber_count(f"stream-{i}") for i in range(200)) == 200
        after = tracemalloc.take_snapshot()
        grown = sum(entry.size_diff for entry in after.compare_to(baseline, "filename"))
    tracemalloc.stop()
    per_subscriber = grown / 200
    # An idle subscriber is an empty deque, a lock and three slots. 4 KiB each is generous.
    assert per_subscriber < 4096, f"{per_subscriber:.0f} bytes per idle subscriber"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
