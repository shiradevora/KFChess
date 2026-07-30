import threading
import time

import pytest

from client.remote_engine import RemoteGameEngine, SERVER_EVENTS_TOPIC
from infrastructure.bus.in_memory_bus import InMemoryEventBus
from protocol.messages import GameStateEvent, JumpDTO, MoveDTO


class FakeGateway:
    """Records send_click/send_jump calls instead of hitting a network."""

    def __init__(self):
        self.clicks: list = []
        self.jumps: list = []

    def send_click(self, x, y):
        self.clicks.append((x, y))

    def send_jump(self, x, y):
        self.jumps.append((x, y))


def _event(clock_ms, board_tokens, board_width, board_height,
           active_moves=(), active_jumps=(), selected_cell=None, game_over=False,
           winner=None):
    return GameStateEvent(
        clock_ms=clock_ms,
        board_tokens=board_tokens,
        board_height=board_height,
        board_width=board_width,
        active_moves=active_moves,
        active_jumps=active_jumps,
        selected_cell=selected_cell,
        game_over=game_over,
        winner=winner,
        empty_token=".",
    )


def _publish_shortly_after(bus, event, delay_s=0.05):
    """Publish on a background thread shortly after this is called.

    RemoteGameEngine.__init__ subscribes synchronously before blocking in
    its poll loop, so a delayed publish from another thread reliably lands
    on that subscription — mirroring how the real ServerGateway delivers
    the first broadcast asynchronously while __init__ is still waiting.
    A bus with no history/replay can't deliver an event published *before*
    the subscription exists, so publishing strictly after construction
    starts (even by a few ms) is required for this to work at all.
    """
    def _publish():
        time.sleep(delay_s)
        bus.publish(SERVER_EVENTS_TOPIC, event)

    threading.Thread(target=_publish, daemon=True).start()


def test_read_only_properties_reflect_the_latest_published_event():
    bus = InMemoryEventBus()
    move = MoveDTO(move_id="m1", piece="wR", start=(0, 0), end=(0, 2),
                    dispatch_ms=0.0, arrival=1000.0)
    jump = JumpDTO(jump_id="m2", piece="bP", cell=(1, 1), end_time=500.0)
    event = _event(
        clock_ms=10.0,
        board_tokens=(("wR", "."), (".", ".")),
        board_width=2, board_height=2,
        active_moves=(move,), active_jumps=(jump,),
        selected_cell=(0, 0), game_over=False,
    )
    _publish_shortly_after(bus, event)

    engine = RemoteGameEngine(FakeGateway(), bus, initial_state_timeout_s=2.0)

    assert engine.board_width == 2
    assert engine.board_height == 2
    assert engine.clock == 10.0
    assert engine.active_moves == (move,)
    assert engine.active_jumps == (jump,)
    assert engine.selected == (0, 0)
    assert engine.game_over is False

    snapshot = engine.snapshot()
    assert snapshot == [["wR", "."], [".", "."]]
    assert isinstance(snapshot, list)
    assert isinstance(snapshot[0], list)


def test_handle_click_and_handle_jump_forward_to_the_gateway():
    bus = InMemoryEventBus()
    gateway = FakeGateway()
    event = _event(clock_ms=1.0, board_tokens=((".",),), board_width=1, board_height=1)
    _publish_shortly_after(bus, event)

    engine = RemoteGameEngine(gateway, bus, initial_state_timeout_s=2.0)
    engine.handle_click(123, 456)
    engine.handle_jump(789, 10)

    assert gateway.clicks == [(123, 456)]
    assert gateway.jumps == [(789, 10)]


def test_a_second_published_event_refreshes_the_properties():
    bus = InMemoryEventBus()
    first = _event(clock_ms=1.0, board_tokens=(("wR",),), board_width=1, board_height=1)
    second = _event(clock_ms=2.0, board_tokens=(("bK",),), board_width=1, board_height=1,
                     game_over=True)
    _publish_shortly_after(bus, first)

    engine = RemoteGameEngine(FakeGateway(), bus, initial_state_timeout_s=2.0)

    assert engine.clock == 1.0
    assert engine.game_over is False
    assert engine.snapshot() == [["wR"]]

    bus.publish(SERVER_EVENTS_TOPIC, second)

    assert engine.clock == 2.0
    assert engine.game_over is True
    assert engine.snapshot() == [["bK"]]


def test_no_event_ever_published_raises_connection_error_after_timeout():
    bus = InMemoryEventBus()

    with pytest.raises(ConnectionError):
        RemoteGameEngine(FakeGateway(), bus, initial_state_timeout_s=0.2)
