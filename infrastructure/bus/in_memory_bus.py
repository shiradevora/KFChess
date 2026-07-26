from __future__ import annotations

import threading
from typing import Callable, Hashable

from ports.event_bus import EventBus, Subscription


class _InMemorySubscription(Subscription):
    def __init__(self, bus: "InMemoryEventBus", topic: Hashable, handler: Callable[[object], None]):
        self._bus = bus
        self._topic = topic
        self._handler = handler

    def unsubscribe(self) -> None:
        self._bus._remove(self._topic, self._handler)


class InMemoryEventBus(EventBus):
    """In-process EventBus backed by a plain dict of topic -> handlers."""

    def __init__(self, on_handler_error: Callable[[Hashable, Exception], None] | None = None):
        self._listeners: dict[Hashable, list[Callable[[object], None]]] = {}
        self._lock = threading.Lock()
        self._on_handler_error = on_handler_error

    def subscribe(self, topic: Hashable, handler: Callable[[object], None]) -> Subscription:
        with self._lock:
            self._listeners.setdefault(topic, []).append(handler)
        return _InMemorySubscription(self, topic, handler)

    def publish(self, topic: Hashable, event: object) -> None:
        with self._lock:
            handlers = list(self._listeners.get(topic, ()))

        for handler in handlers:
            if self._on_handler_error is None:
                handler(event)
                continue
            try:
                handler(event)
            except Exception as exc:
                self._on_handler_error(topic, exc)

    def _remove(self, topic: Hashable, handler: Callable[[object], None]) -> None:
        with self._lock:
            handlers = self._listeners.get(topic)
            if handlers is not None and handler in handlers:
                handlers.remove(handler)
