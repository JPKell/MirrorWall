"""mirrorwall.sse — server-sent events with a gap-free replay-to-live handoff.

This is the subtlest module in the package, and three applications inherit whatever is here, so
the reasoning is written down rather than left in the commit that produced it.

**The handoff.** A client reconnects with ``Last-Event-ID: 41`` and wants every event after 41,
exactly once, in order. Two mistakes are available and both are silent:

* Replay first, then subscribe. Anything produced between the last replayed row and the
  subscription starting is lost, and nothing ever notices — the client simply never sees event 43.
* Subscribe first, then replay, and forward both. Everything produced during replay arrives twice.

The fix is to do both and then reconcile: **subscribe before replaying, and drop from the live
stream anything whose sequence the replay already emitted.** The subscription is open across the
whole replay, so nothing can fall between them; the sequence high-water mark makes the overlap
harmless. Sequences are the application's own monotonic per-stream counter, which is what makes
"already emitted" a decidable question rather than a guess about timing.

**Threads.** The event source is synchronous and database-backed; this handler is ``async def``.
Every call into the source — opening the subscription, each bounded replay batch, closing it —
goes through :func:`anyio.to_thread.run_sync`, here and only here, so no application can put a
blocking ``SELECT`` on the event loop (ADR-0003 §6-8).

The steady-state stream deliberately does **not** use a thread. A subscription is an in-memory,
bounded, thread-safe deque that worker threads push into and the event loop polls; waiting in a
worker thread instead would hold one of the pool's forty slots per connected client, and two
hundred idle subscribers would deadlock every synchronous route handler in the application. The
cost of polling is a bounded latency (half of ``poll_interval_seconds``, 25 ms by default) and no
threads at all, which is the trade that makes the 200-subscriber budget affordable.

**Frames.** Every frame carries the SetSpec event envelope, with one documented exception:
``event: token`` is bare (ADR-0025 §3). A five-field envelope on every token is about a hundred
bytes of overhead per token on the hottest path in the suite, for a frame whose meaning is fully
determined by its event name and its stream.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass, field
from functools import partial
from typing import TYPE_CHECKING, Any, Final, Protocol, runtime_checkable

import anyio
import anyio.to_thread
from setspec import GeneratorInfo, SchemaVersion, dump_envelope
from starlette.responses import StreamingResponse

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator, Mapping, Sequence
    from contextlib import AbstractContextManager

__all__ = [
    "DEFAULT_HEARTBEAT_SECONDS",
    "DEFAULT_POLL_INTERVAL_SECONDS",
    "DEFAULT_QUEUE_SIZE",
    "DEFAULT_REPLAY_BATCH_SIZE",
    "DEFAULT_TERMINAL_EVENTS",
    "EVENT_SCHEMA",
    "EVENT_SCHEMA_VERSION",
    "TOKEN_EVENT",
    "Event",
    "EventBroker",
    "EventSource",
    "Subscription",
    "format_frame",
    "parse_last_event_id",
    "sse_response",
]

logger = logging.getLogger(__name__)

EVENT_SCHEMA: Final = "event.envelope"
"""The schema name every non-``token`` frame declares (ADR-0025 §3)."""

EVENT_SCHEMA_VERSION: Final = SchemaVersion(major=1, minor=0)
"""The event envelope version this build writes."""

TOKEN_EVENT: Final = "token"  # noqa: S105 — an SSE event name, not a credential
"""The one event name whose frame is **not** enveloped. Named here so the exception is a constant
with a docstring rather than a string literal in a branch."""

DEFAULT_HEARTBEAT_SECONDS: Final = 15.0
DEFAULT_QUEUE_SIZE: Final = 256
DEFAULT_REPLAY_BATCH_SIZE: Final = 200
DEFAULT_POLL_INTERVAL_SECONDS: Final = 0.05

DEFAULT_TERMINAL_EVENTS: Final[frozenset[str]] = frozenset()
"""Which event names end a stream, by default none.

An open-ended stream — telemetry, a dashboard — has no terminal event and runs until the client
goes away. A finite one — a generation, a benchmark run — ends with a named event, and a stream
that kept polling after it would hold a connection open forever for a producer that has nothing
left to say. The names are the application's, because only the application knows which of its own
events is the last one."""


@dataclass(frozen=True, slots=True)
class Event:
    """One event, as both an SSE frame and an envelope payload.

    Attributes:
        sequence: The application's own monotonic per-stream counter. It becomes the frame's
            ``id:``, it is what ``Last-Event-ID`` resumes from, and it is what makes the
            replay-to-live handoff decidable. It must be strictly increasing within a stream;
            two events sharing a sequence are indistinguishable to a resuming client.
        type: The SSE event name, e.g. ``"sample.completed"`` or ``"token"``.
        payload: The event body. For an enveloped frame this is the whole event object
            (``event_id``, ``entity``, ``timestamp``, ``message``, ``progress``, ``data``, …) that
            ADR-0025 §3 shows as the envelope's ``payload``; this package adds nothing to it
            except ``sequence`` and ``type``, which it sets so the frame's ``id:`` and the
            payload can never disagree.
    """

    sequence: int
    type: str
    payload: Mapping[str, Any] = field(default_factory=dict)


class Subscription:
    """One client's bounded, in-memory view of a live stream. Thread-safe.

    Worker threads :meth:`publish` into it; the event loop :meth:`poll`s it. Deliberately a plain
    deque under a lock rather than anything awaitable: a subscription is written to from threads
    that know nothing about the event loop (ADR-0003 §5-6), and an awaitable primitive would
    require every publisher to hold a portal into it.

    **Bounded, and it drops.** When the queue is full the *oldest* event is discarded and
    :attr:`dropped` is incremented. A slow consumer therefore costs a fixed amount of memory and
    loses old events, rather than costing unbounded memory and eventually the process. The
    dropped count is not cosmetic: it is what lets the stream tell a client it fell behind
    instead of silently serving it a stream with holes.
    """

    __slots__ = ("_closed", "_dropped", "_lock", "_queue")

    def __init__(self, *, maxlen: int = DEFAULT_QUEUE_SIZE) -> None:
        """Create a subscription holding at most ``maxlen`` undelivered events."""
        if maxlen < 1:
            message = "maxlen must be at least 1"
            raise ValueError(message)
        self._queue: deque[Event] = deque(maxlen=maxlen)
        self._lock = threading.Lock()
        self._dropped = 0
        self._closed = False

    @property
    def dropped(self) -> int:
        """How many events this subscription discarded because the consumer fell behind."""
        with self._lock:
            return self._dropped

    @property
    def closed(self) -> bool:
        """Whether the subscription has been closed."""
        with self._lock:
            return self._closed

    def publish(self, event: Event) -> None:
        """Offer an event to this subscriber. Called from worker threads.

        Never blocks and never raises on a full queue: a publisher is a background worker doing
        real work, and making it wait on the slowest connected browser is how one reader stalls
        an application.
        """
        with self._lock:
            if self._closed:
                return
            if len(self._queue) == self._queue.maxlen:
                self._queue.popleft()
                self._dropped += 1
            self._queue.append(event)

    def poll(self) -> Event | None:
        """Take the next undelivered event, or ``None`` if there is none. Never blocks."""
        with self._lock:
            return self._queue.popleft() if self._queue else None

    def close(self) -> None:
        """Close the subscription and discard anything still queued."""
        with self._lock:
            self._closed = True
            self._queue.clear()


@runtime_checkable
class EventSource(Protocol):
    """What an application supplies so its events can be streamed.

    Synchronous and typically database-backed, by design (ADR-0003 §3): an application implements
    it over its own repositories, and :func:`sse_response` owns the thread dispatch so no
    application has to remember to.
    """

    def replay(self, *, stream_id: str, after_sequence: int, limit: int) -> Sequence[Event]:
        """Return up to ``limit`` persisted events after ``after_sequence``, in order.

        A **batch**, not an iterator: replay reads in bounded batches rather than one round trip
        per event, and a batch is what a `LIMIT` clause and a thread dispatch both want. Returning
        fewer than ``limit`` means the replay is complete.

        Args:
            stream_id: Which stream.
            after_sequence: Exclusive lower bound.
            limit: The maximum number of events to return.

        Returns:
            The events, ascending by sequence.
        """
        ...

    def subscribe(self, *, stream_id: str) -> AbstractContextManager[Subscription]:
        """Open a live subscription to ``stream_id``.

        The context manager's exit must unregister the subscriber; :func:`sse_response` calls it
        in a shielded scope so a disconnected client still releases its slot.

        Args:
            stream_id: Which stream.

        Returns:
            A context manager yielding the subscription.
        """
        ...


class EventBroker:
    """A thread-safe fan-out from worker threads to connected subscribers.

    The in-memory half of an application's :class:`EventSource`: the application persists an event
    and then publishes it here, and the steady-state stream is served from this fan-out without
    touching the database at all. Supplied by this package rather than reimplemented three times,
    because "bounded queue, drop the oldest, unregister on exit" is exactly the code that is easy
    to get subtly wrong once per application.
    """

    __slots__ = ("_lock", "_queue_size", "_streams")

    def __init__(self, *, queue_size: int = DEFAULT_QUEUE_SIZE) -> None:
        """Create a broker whose subscriptions each hold at most ``queue_size`` events."""
        self._streams: dict[str, set[Subscription]] = {}
        self._lock = threading.Lock()
        self._queue_size = queue_size

    def publish(self, stream_id: str, event: Event) -> None:
        """Offer ``event`` to every current subscriber of ``stream_id``. Called from any thread."""
        with self._lock:
            subscribers = list(self._streams.get(stream_id, ()))
        for subscription in subscribers:
            subscription.publish(event)

    def subscriber_count(self, stream_id: str) -> int:
        """How many subscribers ``stream_id`` currently has."""
        with self._lock:
            return len(self._streams.get(stream_id, ()))

    @contextmanager
    def subscribe(self, *, stream_id: str) -> Iterator[Subscription]:
        """Register a subscriber for the duration of the block, and unregister on exit."""
        subscription = Subscription(maxlen=self._queue_size)
        with self._lock:
            self._streams.setdefault(stream_id, set()).add(subscription)
        try:
            yield subscription
        finally:
            with self._lock:
                subscribers = self._streams.get(stream_id)
                if subscribers is not None:
                    subscribers.discard(subscription)
                    if not subscribers:
                        del self._streams[stream_id]
            subscription.close()


def parse_last_event_id(last_event_id: str | None) -> int:
    """Turn a ``Last-Event-ID`` header into a sequence to resume after.

    A header a client controls is never trusted to be a number. Anything unparseable or negative
    resumes from the beginning of the stream rather than raising: a reconnecting browser with a
    corrupted header should get the whole stream, not a 500.

    Args:
        last_event_id: The header value, or ``None`` on a first connection.

    Returns:
        The exclusive lower bound, ``0`` when there is nothing usable to resume from.
    """
    if not last_event_id:
        return 0
    try:
        parsed = int(last_event_id.strip())
    except ValueError:
        return 0
    return max(parsed, 0)


def format_frame(event: Event, *, generator: GeneratorInfo) -> str:
    """Render one event as an SSE frame.

    Every frame is enveloped except ``event: token``, which is bare — the one documented exception
    (ADR-0025 §3). The exception is checked against :data:`TOKEN_EVENT` alone, so it can never
    widen by accident to some other event that happens to be on a hot path.

    ``sequence`` and ``type`` are written into the envelope payload here rather than trusted from
    the caller, so the frame's ``id:`` and the payload's own idea of its sequence cannot disagree.

    Args:
        event: The event.
        generator: The **producing application**, not this package: an envelope's generator is
            what makes a document self-describing months later, and MirrorWall did not produce it.

    Returns:
        The complete frame, terminated by a blank line.
    """
    if event.type == TOKEN_EVENT:
        data = json.dumps(dict(event.payload), separators=(",", ":"), sort_keys=True)
    else:
        data = dump_envelope(
            {**dict(event.payload), "sequence": event.sequence, "type": event.type},
            schema=EVENT_SCHEMA,
            version=EVENT_SCHEMA_VERSION,
            generator=generator,
        )
    return f"id: {event.sequence}\nevent: {event.type}\ndata: {data}\n\n"


def _error_frame(sequence: int, generator: GeneratorInfo, message: str) -> str:
    """The terminal frame a stream ends with when its source fails.

    Enveloped like any other non-``token`` frame: a client that sees this knows the stream ended
    for a reason rather than watching a connection go quiet and guessing.
    """
    return format_frame(
        Event(
            sequence=sequence,
            type="error",
            payload={"code": "STREAM_FAILED", "message": message},
        ),
        generator=generator,
    )


async def _frames(
    source: EventSource,
    *,
    stream_id: str,
    last_event_id: str | None,
    generator: GeneratorInfo,
    heartbeat_seconds: float,
    replay_batch_size: int,
    poll_interval_seconds: float,
    terminal_events: frozenset[str],
) -> AsyncIterator[str]:
    """Produce the frames of one stream: replay, then live, with the handoff reconciled."""
    highest = parse_last_event_id(last_event_id)
    manager: AbstractContextManager[Subscription] | None = None
    subscription: Subscription | None = None
    try:
        # Subscribe FIRST. Everything produced from this instant is captured, so nothing can fall
        # into the gap between the end of the replay and the start of the live stream.
        manager = await anyio.to_thread.run_sync(partial(source.subscribe, stream_id=stream_id))
        subscription = await anyio.to_thread.run_sync(manager.__enter__)

        while True:
            batch = await anyio.to_thread.run_sync(
                partial(
                    source.replay,
                    stream_id=stream_id,
                    after_sequence=highest,
                    limit=replay_batch_size,
                )
            )
            for event in batch:
                if event.sequence <= highest:
                    continue
                yield format_frame(event, generator=generator)
                highest = event.sequence
                if event.type in terminal_events:
                    return
            if len(batch) < replay_batch_size:
                break

        last_beat = time.monotonic()
        while True:
            live = subscription.poll()
            if live is None:
                now = time.monotonic()
                if now - last_beat >= heartbeat_seconds:
                    # A comment frame: it costs four bytes, it is ignored by every client, and
                    # writing it is what makes a dead connection fail rather than linger.
                    yield ": heartbeat\n\n"
                    last_beat = now
                await anyio.sleep(poll_interval_seconds)
                continue
            # The replay/live overlap: an event the replay already emitted is dropped here, which
            # is why subscribing early cannot produce a duplicate.
            if live.sequence <= highest:
                continue
            yield format_frame(live, generator=generator)
            highest = live.sequence
            if live.type in terminal_events:
                return
    except Exception as exc:  # noqa: BLE001 — any source failure becomes one terminal frame
        logger.exception("sse.source_failed", extra={"stream_id": stream_id})
        yield _error_frame(highest + 1, generator, f"The event source failed: {exc}")
    finally:
        if manager is not None:
            # Shielded: the generator is being closed because the client disconnected, so the
            # surrounding scope is already cancelled and an unshielded await would abandon the
            # subscription registered above — leaking a slot per dropped connection.
            with anyio.CancelScope(shield=True):
                await anyio.to_thread.run_sync(partial(manager.__exit__, None, None, None))


def sse_response(
    source: EventSource,
    *,
    stream_id: str,
    last_event_id: str | None,
    generator: GeneratorInfo,
    heartbeat_seconds: float = DEFAULT_HEARTBEAT_SECONDS,
    queue_size: int = DEFAULT_QUEUE_SIZE,
    replay_batch_size: int = DEFAULT_REPLAY_BATCH_SIZE,
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
    terminal_events: frozenset[str] = DEFAULT_TERMINAL_EVENTS,
) -> StreamingResponse:
    """Stream ``stream_id``'s events, resuming after ``last_event_id`` with no gap or duplicate.

    Args:
        source: The application's event source.
        stream_id: Which stream.
        last_event_id: The client's ``Last-Event-ID`` header, or ``None`` on a first connection.
            Never trusted to be a number; anything unusable resumes from the beginning.
        generator: The producing application's own name and version, for the envelope.
        heartbeat_seconds: How often a comment frame is written when nothing else is.
        queue_size: How many undelivered events a subscriber holds before the oldest is dropped.
            Applies to the subscriptions the source's own broker creates; passed through so an
            application can configure one place rather than two.
        replay_batch_size: The `LIMIT` each replay round trip uses.
        poll_interval_seconds: How long the loop sleeps when the subscription is empty. Half of
            this is the median added latency of a live event; it buys the stream costing no
            threadpool slot at all while idle.
        terminal_events: Event names after which the stream closes. Empty (the default) means the
            stream is open-ended and runs until the client disconnects.

    Returns:
        The streaming response, with the headers that stop a proxy from buffering it into
        uselessness.
    """
    return StreamingResponse(
        _frames(
            source,
            stream_id=stream_id,
            last_event_id=last_event_id,
            generator=generator,
            heartbeat_seconds=heartbeat_seconds,
            replay_batch_size=replay_batch_size,
            poll_interval_seconds=poll_interval_seconds,
            terminal_events=terminal_events,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store",
            "Connection": "keep-alive",
            # Nginx buffers a proxied response by default, which turns a live stream into one
            # large delivery at the end. This is the documented way to turn that off.
            "X-Accel-Buffering": "no",
        },
    )
