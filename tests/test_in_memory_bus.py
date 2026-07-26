import pytest

from infrastructure.bus.in_memory_bus import InMemoryEventBus


def test_subscribe_and_publish_delivers_the_event():
    bus = InMemoryEventBus()
    received = []
    bus.subscribe("topic", received.append)

    sentinel = object()
    bus.publish("topic", sentinel)

    assert received == [sentinel]


def test_two_handlers_on_same_topic_both_receive_event():
    bus = InMemoryEventBus()
    received_a = []
    received_b = []
    bus.subscribe("topic", received_a.append)
    bus.subscribe("topic", received_b.append)

    bus.publish("topic", "payload")

    assert received_a == ["payload"]
    assert received_b == ["payload"]


def test_publish_with_no_listeners_does_not_raise():
    bus = InMemoryEventBus()

    bus.publish("nobody-home", "payload")


def test_unsubscribe_stops_that_handler_but_not_others():
    bus = InMemoryEventBus()
    received_a = []
    received_b = []
    subscription_a = bus.subscribe("topic", received_a.append)
    bus.subscribe("topic", received_b.append)

    subscription_a.unsubscribe()
    bus.publish("topic", "payload")

    assert received_a == []
    assert received_b == ["payload"]


def test_handler_exception_does_not_block_later_handlers():
    errors = []
    bus = InMemoryEventBus(on_handler_error=lambda topic, exc: errors.append((topic, exc)))
    received = []

    boom = RuntimeError("boom")

    def failing_handler(event):
        raise boom

    bus.subscribe("topic", failing_handler)
    bus.subscribe("topic", received.append)

    bus.publish("topic", "payload")

    assert received == ["payload"]
    assert errors == [("topic", boom)]


def test_handler_exception_propagates_when_no_error_callback_given():
    bus = InMemoryEventBus()

    def failing_handler(event):
        raise RuntimeError("boom")

    bus.subscribe("topic", failing_handler)

    with pytest.raises(RuntimeError):
        bus.publish("topic", "payload")


def test_subscribe_and_publish_with_non_str_hashable_topic():
    bus = InMemoryEventBus()
    received = []
    topic = ("session-1", "move")
    bus.subscribe(topic, received.append)

    bus.publish(topic, "payload")

    assert received == ["payload"]


def test_publish_does_not_reach_handler_on_different_topic():
    bus = InMemoryEventBus()
    received = []
    bus.subscribe("topic-a", received.append)

    bus.publish("topic-b", "payload")

    assert received == []
