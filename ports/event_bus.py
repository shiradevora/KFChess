from abc import ABC, abstractmethod
from typing import Callable, Hashable


class Subscription:
    """Handle returned by EventBus.subscribe(), used to cancel that one subscription."""

    def unsubscribe(self) -> None:
        raise NotImplementedError


class EventBus(ABC):
    """Publish/subscribe mediator between event producers and consumers.

    Unlike the Observer pattern, publishers hold no reference to subscribers
    (and vice versa): both sides only know about a "topic" name, and the bus
    routes events between them. This keeps producers and consumers decoupled
    and swappable independently of one another.
    """

    @abstractmethod
    def publish(self, topic: Hashable, event: object) -> None:
        raise NotImplementedError

    @abstractmethod
    def subscribe(self, topic: Hashable, handler: Callable[[object], None]) -> Subscription:
        raise NotImplementedError
