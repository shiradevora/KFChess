import asyncio
import json

from board.text_board import TextBoardRepresentation
from config import settings
from rules.game_conditions import KingCaptureWinCondition, LastRankPromotion
from rules.rule_registry import build_default_registry
from game.engine import GameEngine
from application.game_session import GameSession
from infrastructure.bus.in_memory_bus import InMemoryEventBus
from ports.transport import Connection, ConnectionClosed
from protocol.codec import decode, encode
from protocol.messages import ClickCommand, ErrorMessage, GameStateEvent
from server.connection_handler import handle_connection


class FakeConnection(Connection):
    """In-memory Connection backed by asyncio Queues — no real socket."""

    def __init__(self, connection_id="fake-1"):
        self._id = connection_id
        self.inbound = asyncio.Queue()
        self.outbound: list = []

    @property
    def connection_id(self) -> str:
        return self._id

    async def send(self, raw: str) -> None:
        self.outbound.append(raw)

    async def receive(self) -> str:
        item = await self.inbound.get()
        if item is None:
            raise ConnectionClosed("closed by test")
        return item

    async def close(self) -> None:
        pass


class ImmediatelyClosedConnection(Connection):
    """Connection whose send() always raises ConnectionClosed (simulating a
    peer that already disconnected), and whose receive() can be closed via
    the same None-sentinel convention as FakeConnection."""

    def __init__(self, connection_id="closed-1"):
        self._id = connection_id
        self.inbound = asyncio.Queue()
        self.send_attempts = 0

    @property
    def connection_id(self) -> str:
        return self._id

    async def send(self, raw: str) -> None:
        self.send_attempts += 1
        raise ConnectionClosed("send failed: peer already gone")

    async def receive(self) -> str:
        item = await self.inbound.get()
        if item is None:
            raise ConnectionClosed("closed by test")
        return item

    async def close(self) -> None:
        pass


class NullLogger:
    def warning(self, *args, **kwargs):
        pass


def _game_state_event(clock_ms: float) -> GameStateEvent:
    return GameStateEvent(
        clock_ms=clock_ms,
        board_tokens=(),
        board_height=0,
        board_width=0,
        active_moves=(),
        active_jumps=(),
        selected_cell=None,
        game_over=False,
        empty_token=".",
    )


def make_session():
    board = TextBoardRepresentation([["wR", ".", "."], [".", ".", "."], [".", ".", "."]])
    engine = GameEngine(
        board=board,
        rule_registry=build_default_registry(settings),
        win_condition=KingCaptureWinCondition(),
        promotion_rule=LastRankPromotion(),
        config=settings,
    )
    bus = InMemoryEventBus()
    session = GameSession(session_id="test", engine=engine, event_bus=bus)
    return session, bus


def run_async(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_click_command_results_in_game_state_event_sent_back():
    session, bus = make_session()
    connection = FakeConnection()

    async def scenario():
        task = asyncio.ensure_future(handle_connection(connection, session, bus, NullLogger()))
        await connection.inbound.put(encode(ClickCommand(x=0, y=0)))
        await asyncio.sleep(0.05)
        await connection.inbound.put(None)  # signal close
        await task

    run_async(scenario())

    payloads = [json.loads(raw) for raw in connection.outbound]
    assert any(payload.get("type") == "game_state" for payload in payloads)


def test_malformed_json_gets_error_reply_and_does_not_stop_the_handler():
    session, bus = make_session()
    connection = FakeConnection()

    async def scenario():
        task = asyncio.ensure_future(handle_connection(connection, session, bus, NullLogger()))
        await connection.inbound.put("{not valid json")
        await asyncio.sleep(0.05)
        await connection.inbound.put(encode(ClickCommand(x=0, y=0)))
        await asyncio.sleep(0.05)
        await connection.inbound.put(None)  # signal close
        await task

    run_async(scenario())

    decoded_errors = [
        decode(raw) for raw in connection.outbound
        if json.loads(raw).get("type") == "error"
    ]
    payloads = [json.loads(raw) for raw in connection.outbound]

    assert len(decoded_errors) == 1
    assert isinstance(decoded_errors[0], ErrorMessage)
    # The handler kept processing after the bad message: the later, valid
    # ClickCommand still produced a GameStateEvent reply.
    assert any(payload.get("type") == "game_state" for payload in payloads)


def test_rapid_back_to_back_publishes_are_both_sent_in_order_not_dropped():
    """Regression test for the create_task-per-event race: publishing two
    events on the bus synchronously, back-to-back, before anything yields
    control, must still result in two separate, in-order send() calls via
    the single writer — not interleaved sends and not a dropped event."""
    session, bus = make_session()
    connection = FakeConnection()
    topic = f"session:{session.session_id}"

    async def scenario():
        task = asyncio.ensure_future(handle_connection(connection, session, bus, NullLogger()))
        await asyncio.sleep(0)  # let handle_connection subscribe and start its writer

        # Two publishes with no await in between — this is exactly the
        # rapid-fire pattern (e.g. periodic tick landing right after a
        # click) that used to race two concurrent send() calls.
        bus.publish(topic, _game_state_event(clock_ms=1.0))
        bus.publish(topic, _game_state_event(clock_ms=2.0))

        await asyncio.sleep(0.05)
        await connection.inbound.put(None)  # signal close
        await task

    run_async(scenario())

    game_state_payloads = [
        json.loads(raw) for raw in connection.outbound
        if json.loads(raw).get("type") == "game_state"
    ]
    assert [payload["clock_ms"] for payload in game_state_payloads] == [1.0, 2.0]


def test_handler_returns_cleanly_and_unsubscribes_when_send_raises_connection_closed():
    session, bus = make_session()
    connection = ImmediatelyClosedConnection()
    topic = f"session:{session.session_id}"

    async def scenario():
        task = asyncio.ensure_future(handle_connection(connection, session, bus, NullLogger()))
        await asyncio.sleep(0)

        bus.publish(topic, _game_state_event(clock_ms=1.0))  # writer's send() raises, writer returns
        await asyncio.sleep(0.05)
        await connection.inbound.put(None)  # end the receive loop too

        await task  # must not raise — no unhandled exception from handle_connection

    run_async(scenario())

    attempts_before = connection.send_attempts
    bus.publish(topic, _game_state_event(clock_ms=2.0))  # subscription should be gone by now
    assert connection.send_attempts == attempts_before
