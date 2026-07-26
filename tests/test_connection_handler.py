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
from protocol.messages import ClickCommand, ErrorMessage
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


class NullLogger:
    def warning(self, *args, **kwargs):
        pass


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
