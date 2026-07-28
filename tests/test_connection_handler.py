from __future__ import annotations

import asyncio
import json

from board.text_board import TextBoardRepresentation
from config import settings
from rules.game_conditions import KingCaptureWinCondition, LastRankPromotion
from rules.rule_registry import build_default_registry
from game.engine import GameEngine
from application.auth_service import AuthService
from application.game_session import GameSession
from infrastructure.bus.in_memory_bus import InMemoryEventBus
from ports.transport import Connection, ConnectionClosed
from ports.user_repository import UserRecord, UserRepository
from protocol.codec import decode, encode
from protocol.messages import ClickCommand, ErrorMessage, GameStateEvent, LoginCommand, RegisterCommand
from server.connection_handler import handle_connection


class FakeConnection(Connection):
    """In-memory Connection backed by asyncio Queues — no real socket."""

    def __init__(self, connection_id="fake-1"):
        self._id = connection_id
        self.inbound = asyncio.Queue()
        self.outbound: list = []
        self.closed = False

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
        self.closed = True


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
    def info(self, *args, **kwargs):
        pass

    def warning(self, *args, **kwargs):
        pass


class FakeUserRepository(UserRepository):
    """Dict-backed in-memory UserRepository — same style as
    tests/test_auth_service.py's fake; duplicated here to keep this test
    file self-contained."""

    def __init__(self):
        self._users: dict[str, UserRecord] = {}

    async def find_by_username(self, username: str) -> UserRecord | None:
        return self._users.get(username)

    async def create_user(self, username: str, password_hash: str, salt: str) -> UserRecord:
        record = UserRecord(username=username, password_hash=password_hash, salt=salt, rating=1200)
        self._users[username] = record
        return record


def make_auth_service() -> AuthService:
    return AuthService(FakeUserRepository())


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


def test_register_then_click_results_in_game_state_event_sent_back():
    session, bus = make_session()
    connection = FakeConnection()
    auth_service = make_auth_service()

    async def scenario():
        task = asyncio.ensure_future(
            handle_connection(connection, session, bus, NullLogger(), auth_service))
        await connection.inbound.put(encode(RegisterCommand(username="alice", password="hunter2")))
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
    auth_service = make_auth_service()

    async def scenario():
        task = asyncio.ensure_future(
            handle_connection(connection, session, bus, NullLogger(), auth_service))
        await connection.inbound.put(encode(RegisterCommand(username="alice", password="hunter2")))
        await asyncio.sleep(0.05)
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
    auth_service = make_auth_service()
    topic = f"session:{session.session_id}"

    async def scenario():
        task = asyncio.ensure_future(
            handle_connection(connection, session, bus, NullLogger(), auth_service))
        await connection.inbound.put(encode(RegisterCommand(username="alice", password="hunter2")))
        await asyncio.sleep(0)  # let handle_connection consume the auth, subscribe, and start its writer

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
    auth_service = make_auth_service()
    topic = f"session:{session.session_id}"

    async def scenario():
        task = asyncio.ensure_future(
            handle_connection(connection, session, bus, NullLogger(), auth_service))
        await connection.inbound.put(encode(RegisterCommand(username="alice", password="hunter2")))
        await asyncio.sleep(0)

        bus.publish(topic, _game_state_event(clock_ms=1.0))  # writer's send() raises, writer returns
        await asyncio.sleep(0.05)
        await connection.inbound.put(None)  # end the receive loop too

        await task  # must not raise — no unhandled exception from handle_connection

    run_async(scenario())

    attempts_before = connection.send_attempts
    bus.publish(topic, _game_state_event(clock_ms=2.0))  # subscription should be gone by now
    assert connection.send_attempts == attempts_before


def test_login_then_click_is_processed_normally():
    session, bus = make_session()
    connection = FakeConnection()
    auth_service = make_auth_service()
    run_async(auth_service.register("alice", "hunter2"))

    async def scenario():
        task = asyncio.ensure_future(
            handle_connection(connection, session, bus, NullLogger(), auth_service))
        await connection.inbound.put(encode(LoginCommand(username="alice", password="hunter2")))
        await connection.inbound.put(encode(ClickCommand(x=0, y=0)))
        await asyncio.sleep(0.05)
        await connection.inbound.put(None)  # signal close
        await task

    run_async(scenario())

    payloads = [json.loads(raw) for raw in connection.outbound]
    assert any(payload.get("type") == "game_state" for payload in payloads)
    assert connection.closed is False


def test_failed_login_retries_and_eventually_succeeds():
    session, bus = make_session()
    connection = FakeConnection()
    auth_service = make_auth_service()
    run_async(auth_service.register("alice", "correct_password"))

    async def scenario():
        task = asyncio.ensure_future(
            handle_connection(connection, session, bus, NullLogger(), auth_service))
        await connection.inbound.put(encode(LoginCommand(username="alice", password="wrong_password")))
        await asyncio.sleep(0.05)
        await connection.inbound.put(encode(LoginCommand(username="alice", password="correct_password")))
        await connection.inbound.put(encode(ClickCommand(x=0, y=0)))
        await asyncio.sleep(0.05)
        await connection.inbound.put(None)
        await task

    run_async(scenario())

    payloads = [json.loads(raw) for raw in connection.outbound]
    error_payloads = [p for p in payloads if p.get("type") == "error"]

    assert len(error_payloads) == 1
    assert error_payloads[0]["message"] == "Invalid username or password"
    assert any(payload.get("type") == "game_state" for payload in payloads)
    # A failed login attempt during the handshake must not close the
    # connection — the client gets to retry.
    assert connection.closed is False


def test_login_with_empty_username_gets_generic_invalid_credentials_error():
    session, bus = make_session()
    connection = FakeConnection()
    auth_service = make_auth_service()

    async def scenario():
        task = asyncio.ensure_future(
            handle_connection(connection, session, bus, NullLogger(), auth_service))
        await connection.inbound.put(encode(LoginCommand(username="", password="whatever")))
        await asyncio.sleep(0.05)
        await connection.inbound.put(None)
        await task

    run_async(scenario())

    payloads = [json.loads(raw) for raw in connection.outbound]
    error_payloads = [p for p in payloads if p.get("type") == "error"]

    assert len(error_payloads) == 1
    assert error_payloads[0]["message"] == "Invalid username or password"
    assert not any(payload.get("type") == "game_state" for payload in payloads)
    assert connection.closed is False


def test_click_before_authentication_gets_retry_prompt_and_handshake_can_still_succeed():
    """Regression test for the B2 handshake behavior change: an unrecognized
    message type before authentication gets an ErrorMessage but does NOT
    close the connection — unlike B1, the client gets to retry."""
    session, bus = make_session()
    connection = FakeConnection()
    auth_service = make_auth_service()

    click_calls: list = []
    original_handle_click = session.handle_click

    def _spy_handle_click(x, y):
        click_calls.append((x, y))
        return original_handle_click(x, y)

    session.handle_click = _spy_handle_click

    async def scenario():
        task = asyncio.ensure_future(
            handle_connection(connection, session, bus, NullLogger(), auth_service))
        await connection.inbound.put(encode(ClickCommand(x=0, y=0)))  # too early — not authenticated yet
        await asyncio.sleep(0.05)
        await connection.inbound.put(encode(RegisterCommand(username="alice", password="hunter2")))
        await connection.inbound.put(encode(ClickCommand(x=1, y=1)))  # now authenticated
        await asyncio.sleep(0.05)
        await connection.inbound.put(None)
        await task

    run_async(scenario())

    payloads = [json.loads(raw) for raw in connection.outbound]

    assert any(payload.get("type") == "error" for payload in payloads)
    assert any(payload.get("type") == "game_state" for payload in payloads)
    assert connection.closed is False
    # The click sent before authentication never reached game logic; only
    # the one sent after the successful register did.
    assert click_calls == [(1, 1)]
