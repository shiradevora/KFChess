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
from application.matchmaking_service import MatchResult
from infrastructure.bus.in_memory_bus import InMemoryEventBus
from ports.transport import Connection, ConnectionClosed
from ports.user_repository import UserRecord, UserRepository
from protocol.codec import decode, encode
from protocol.messages import (
    ClickCommand,
    ErrorMessage,
    GameStateEvent,
    LoginCommand,
    PlayCommand,
    RegisterCommand,
)
from server.connection_handler import _NOT_IN_A_MATCH_MESSAGE, _run_match_loop, handle_connection
from server.session_registry import SessionRegistry


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


class ConcurrentSendDetectingConnection(Connection):
    """Connection whose send() genuinely yields mid-call (an internal
    await) and tracks whether it's ever re-entered while a previous call is
    still in flight. Unlike the plain synchronous FakeConnection above
    (whose send() has no internal await and therefore can never actually
    observe two overlapping logical senders), this fake can catch a
    regression where something bypasses the outbox/writer and calls
    connection.send() directly, racing the writer's own send()."""

    def __init__(self, connection_id="concurrent-1"):
        self._id = connection_id
        self.inbound = asyncio.Queue()
        self.outbound: list = []
        self._sending = False
        self.concurrent_sends_detected = False

    @property
    def connection_id(self) -> str:
        return self._id

    async def send(self, raw: str) -> None:
        if self._sending:
            self.concurrent_sends_detected = True
        self._sending = True
        try:
            await asyncio.sleep(0.01)
            self.outbound.append(raw)
        finally:
            self._sending = False

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

    async def update_rating(self, username: str, new_rating: int) -> None:
        record = self._users[username]
        self._users[username] = UserRecord(
            username=record.username, password_hash=record.password_hash,
            salt=record.salt, rating=new_rating,
        )


class FakeMatchmakingService:
    """Returns a pre-set MatchResult immediately — no real queueing/pairing.
    For tests that only care about connection_handler's lobby wiring, not
    MatchmakingService's own pairing logic (see test_matchmaking_service.py
    for that)."""

    def __init__(self, result: MatchResult):
        self._result = result

    async def enqueue_and_wait(self, username: str, rating: int) -> MatchResult:
        return self._result


class TimeoutThenMatchService:
    """First call reports no match found; every call after that succeeds
    with the given result — for testing the lobby's timeout-then-retry
    path without a real 60s wait."""

    def __init__(self, success_result: MatchResult):
        self._success_result = success_result
        self._calls = 0

    async def enqueue_and_wait(self, username: str, rating: int) -> MatchResult:
        self._calls += 1
        if self._calls == 1:
            return MatchResult(matched=False, opponent_username=None, session_id=None)
        return self._success_result


def make_auth_service_and_repository() -> tuple[AuthService, FakeUserRepository]:
    repository = FakeUserRepository()
    return AuthService(repository), repository


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
        winner=None,
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


# ----------------------------------------------------------------------
# _run_match_loop: the click/jump <-> GameSession bridge, tested directly
# (bypassing authentication and matchmaking, which aren't its concern).
# ----------------------------------------------------------------------

def test_click_command_results_in_game_state_event_sent_back():
    session, bus = make_session()
    connection = FakeConnection()

    async def scenario():
        task = asyncio.ensure_future(_run_match_loop(connection, session, bus, NullLogger(), "white"))
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
        task = asyncio.ensure_future(_run_match_loop(connection, session, bus, NullLogger(), "white"))
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
        task = asyncio.ensure_future(_run_match_loop(connection, session, bus, NullLogger(), "white"))
        await asyncio.sleep(0)  # let _run_match_loop subscribe and start its writer

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


def test_malformed_message_and_bus_publish_on_the_same_tick_dont_race_the_writer():
    """Regression test for the DecodeError handler bypassing the outbox:
    _run_match_loop() used to send its ErrorMessage directly on the
    connection instead of through the outbox/writer, which could race a
    concurrent send() from the writer draining a bus-published event — the
    same bug class already fixed for the outbound writer (server-side, see
    test_rapid_back_to_back_publishes_are_both_sent_in_order_not_dropped
    above) and for ServerGateway (client-side). A malformed inbound message
    and a bus publish landing on the same tick, with no yield in between,
    must both be delivered as two separate, non-interleaved send() calls —
    not dropped, not corrupted, and never two sends in flight at once."""
    session, bus = make_session()
    connection = ConcurrentSendDetectingConnection()
    topic = f"session:{session.session_id}"

    async def scenario():
        task = asyncio.ensure_future(_run_match_loop(connection, session, bus, NullLogger(), "white"))
        await asyncio.sleep(0)  # let _run_match_loop subscribe and start its writer

        # A malformed inbound message and a bus publish, back-to-back with
        # no await in between — both replies must go through the single
        # writer, not race each other.
        await connection.inbound.put("{not valid json")
        bus.publish(topic, _game_state_event(clock_ms=1.0))

        await asyncio.sleep(0.1)
        await connection.inbound.put(None)  # signal close
        await task

    run_async(scenario())

    payloads = [json.loads(raw) for raw in connection.outbound]
    error_payloads = [p for p in payloads if p.get("type") == "error"]
    game_state_payloads = [p for p in payloads if p.get("type") == "game_state"]

    assert connection.concurrent_sends_detected is False
    assert len(connection.outbound) == 2
    assert len(error_payloads) == 1
    assert len(game_state_payloads) == 1
    assert game_state_payloads[0]["clock_ms"] == 1.0


def test_handler_returns_cleanly_and_unsubscribes_when_send_raises_connection_closed():
    session, bus = make_session()
    connection = ImmediatelyClosedConnection()
    topic = f"session:{session.session_id}"

    async def scenario():
        task = asyncio.ensure_future(_run_match_loop(connection, session, bus, NullLogger(), "white"))
        await asyncio.sleep(0)

        bus.publish(topic, _game_state_event(clock_ms=1.0))  # writer's send() raises, writer returns
        await asyncio.sleep(0.05)
        await connection.inbound.put(None)  # end the receive loop too

        await task  # must not raise — no unhandled exception from handle_connection

    run_async(scenario())

    attempts_before = connection.send_attempts
    bus.publish(topic, _game_state_event(clock_ms=2.0))  # subscription should be gone by now
    assert connection.send_attempts == attempts_before


def test_click_with_wrong_acting_color_is_rejected_by_the_session():
    """make_session()'s board is all-white ("wR" pieces) — a connection
    whose acting_color is resolved to "black" must have its click on that
    white piece rejected, with no game_state reply at all (GameSession
    never reaches _publish_state() for a rejected action)."""
    session, bus = make_session()
    connection = FakeConnection()

    async def scenario():
        task = asyncio.ensure_future(
            _run_match_loop(connection, session, bus, NullLogger(), "black"))
        await connection.inbound.put(encode(ClickCommand(x=0, y=0)))  # (0,0) holds "wR"
        await asyncio.sleep(0.05)
        await connection.inbound.put(None)
        await task

    run_async(scenario())

    payloads = [json.loads(raw) for raw in connection.outbound]
    assert len(payloads) == 1
    assert payloads[0]["type"] == "error"


def test_click_with_matching_acting_color_succeeds():
    session, bus = make_session()
    connection = FakeConnection()

    async def scenario():
        task = asyncio.ensure_future(
            _run_match_loop(connection, session, bus, NullLogger(), "white"))
        await connection.inbound.put(encode(ClickCommand(x=0, y=0)))  # (0,0) holds "wR"
        await asyncio.sleep(0.05)
        await connection.inbound.put(None)
        await task

    run_async(scenario())

    payloads = [json.loads(raw) for raw in connection.outbound]
    assert any(p.get("type") == "game_state" and p.get("selected_cell") == [0, 0]
               for p in payloads)


# ----------------------------------------------------------------------
# handle_connection: full auth -> lobby -> match flow.
# ----------------------------------------------------------------------

def test_register_gets_auth_success_event():
    bus = InMemoryEventBus()
    session_registry = SessionRegistry(bus)
    matchmaking_service = FakeMatchmakingService(
        MatchResult(matched=False, opponent_username=None, session_id=None))
    connection = FakeConnection()
    auth_service, user_repository = make_auth_service_and_repository()

    async def scenario():
        task = asyncio.ensure_future(handle_connection(
            connection, bus, NullLogger(), auth_service, matchmaking_service,
            session_registry, user_repository))
        await connection.inbound.put(encode(RegisterCommand(username="alice", password="hunter2")))
        await asyncio.sleep(0.05)
        await connection.inbound.put(None)
        await task

    run_async(scenario())

    payloads = [json.loads(raw) for raw in connection.outbound]
    assert any(p.get("type") == "auth_success" and p.get("username") == "alice" for p in payloads)


def test_failed_login_retries_and_eventually_succeeds():
    bus = InMemoryEventBus()
    session_registry = SessionRegistry(bus)
    matchmaking_service = FakeMatchmakingService(
        MatchResult(matched=False, opponent_username=None, session_id=None))
    connection = FakeConnection()
    auth_service, user_repository = make_auth_service_and_repository()
    run_async(auth_service.register("alice", "correct_password"))

    async def scenario():
        task = asyncio.ensure_future(handle_connection(
            connection, bus, NullLogger(), auth_service, matchmaking_service,
            session_registry, user_repository))
        await connection.inbound.put(encode(LoginCommand(username="alice", password="wrong_password")))
        await asyncio.sleep(0.05)
        await connection.inbound.put(encode(LoginCommand(username="alice", password="correct_password")))
        await asyncio.sleep(0.05)
        await connection.inbound.put(None)
        await task

    run_async(scenario())

    payloads = [json.loads(raw) for raw in connection.outbound]
    error_payloads = [p for p in payloads if p.get("type") == "error"]

    assert len(error_payloads) == 1
    assert error_payloads[0]["message"] == "Invalid username or password"
    assert any(p.get("type") == "auth_success" for p in payloads)
    # A failed login attempt during the handshake must not close the
    # connection — the client gets to retry.
    assert connection.closed is False


def test_click_before_authentication_gets_retry_prompt_and_handshake_can_still_succeed():
    """An unrecognized message type before authentication gets an
    ErrorMessage but does NOT close the connection — the client gets to
    retry, and never reaches the lobby (no AuthSuccessEvent) until it does."""
    bus = InMemoryEventBus()
    session_registry = SessionRegistry(bus)
    matchmaking_service = FakeMatchmakingService(
        MatchResult(matched=False, opponent_username=None, session_id=None))
    connection = FakeConnection()
    auth_service, user_repository = make_auth_service_and_repository()

    async def scenario():
        task = asyncio.ensure_future(handle_connection(
            connection, bus, NullLogger(), auth_service, matchmaking_service,
            session_registry, user_repository))
        await connection.inbound.put(encode(ClickCommand(x=0, y=0)))  # too early — not authenticated yet
        await asyncio.sleep(0.05)
        await connection.inbound.put(encode(RegisterCommand(username="alice", password="hunter2")))
        await asyncio.sleep(0.05)
        await connection.inbound.put(None)
        await task

    run_async(scenario())

    payloads = [json.loads(raw) for raw in connection.outbound]
    types_in_order = [p.get("type") for p in payloads]

    # The early click gets one error, then (and only then) does the
    # register attempt succeed and produce the auth_success confirmation.
    assert types_in_order == ["error", "auth_success"]
    assert connection.closed is False


# ----------------------------------------------------------------------
# handle_connection: lobby (play/matchmaking) flow.
# ----------------------------------------------------------------------

def test_play_then_matched_then_click_is_processed_normally():
    bus = InMemoryEventBus()
    session_registry = SessionRegistry(bus)
    connection = FakeConnection()
    auth_service, user_repository = make_auth_service_and_repository()
    session_ids: list = []

    async def scenario():
        # create_session() uses asyncio.create_task internally, so it needs
        # a running loop — it can't be called before run_async(scenario()).
        session_id = session_registry.create_session("alice", "bob")
        session_ids.append(session_id)
        matchmaking_service = FakeMatchmakingService(
            MatchResult(matched=True, opponent_username="bob", session_id=session_id))

        # Color assignment is random — click on whichever back-rank row
        # actually belongs to alice's assigned color, so this test doesn't
        # flake depending on the coin flip (see server/session_registry.py).
        players = session_registry.get_players(session_id)
        row = 7 if players.white_username == "alice" else 0

        task = asyncio.ensure_future(handle_connection(
            connection, bus, NullLogger(), auth_service, matchmaking_service,
            session_registry, user_repository))
        await connection.inbound.put(encode(RegisterCommand(username="alice", password="hunter2")))
        await connection.inbound.put(encode(PlayCommand()))
        await connection.inbound.put(encode(ClickCommand(x=0, y=row * settings.CELL_SIZE)))
        await asyncio.sleep(0.05)
        await connection.inbound.put(None)
        await task

    run_async(scenario())
    session_id = session_ids[0]

    payloads = [json.loads(raw) for raw in connection.outbound]
    assert any(p.get("type") == "auth_success" for p in payloads)
    match_found = [p for p in payloads if p.get("type") == "match_found"]
    assert len(match_found) == 1
    assert match_found[0]["opponent_username"] == "bob"
    assert match_found[0]["session_id"] == session_id
    assert any(p.get("type") == "game_state" for p in payloads)


def test_play_timeout_then_retry_succeeds():
    bus = InMemoryEventBus()
    session_registry = SessionRegistry(bus)
    connection = FakeConnection()
    auth_service, user_repository = make_auth_service_and_repository()

    async def scenario():
        # create_session() uses asyncio.create_task internally, so it needs
        # a running loop — it can't be called before run_async(scenario()).
        session_id = session_registry.create_session("alice", "bob")
        matchmaking_service = TimeoutThenMatchService(
            MatchResult(matched=True, opponent_username="bob", session_id=session_id))

        # Color assignment is random — click on whichever back-rank row
        # actually belongs to alice's assigned color, so this test doesn't
        # flake depending on the coin flip (see server/session_registry.py).
        players = session_registry.get_players(session_id)
        row = 7 if players.white_username == "alice" else 0

        task = asyncio.ensure_future(handle_connection(
            connection, bus, NullLogger(), auth_service, matchmaking_service,
            session_registry, user_repository))
        await connection.inbound.put(encode(RegisterCommand(username="alice", password="hunter2")))
        await connection.inbound.put(encode(PlayCommand()))  # times out — no match
        await asyncio.sleep(0.05)
        await connection.inbound.put(encode(PlayCommand()))  # retry — matches
        await connection.inbound.put(encode(ClickCommand(x=0, y=row * settings.CELL_SIZE)))
        await asyncio.sleep(0.05)
        await connection.inbound.put(None)
        await task

    run_async(scenario())

    payloads = [json.loads(raw) for raw in connection.outbound]
    assert any(p.get("type") == "error" for p in payloads)
    assert any(p.get("type") == "match_found" for p in payloads)
    assert any(p.get("type") == "game_state" for p in payloads)
    assert connection.closed is False


def test_click_before_play_gets_rejection_not_crash():
    bus = InMemoryEventBus()
    session_registry = SessionRegistry(bus)
    matchmaking_service = FakeMatchmakingService(
        MatchResult(matched=False, opponent_username=None, session_id=None))
    connection = FakeConnection()
    auth_service, user_repository = make_auth_service_and_repository()

    async def scenario():
        task = asyncio.ensure_future(handle_connection(
            connection, bus, NullLogger(), auth_service, matchmaking_service,
            session_registry, user_repository))
        await connection.inbound.put(encode(RegisterCommand(username="alice", password="hunter2")))
        await connection.inbound.put(encode(ClickCommand(x=0, y=0)))  # not in a match yet
        await asyncio.sleep(0.05)
        await connection.inbound.put(None)
        await task

    run_async(scenario())

    payloads = [json.loads(raw) for raw in connection.outbound]
    error_payloads = [p for p in payloads if p.get("type") == "error"]

    assert any(p["message"] == _NOT_IN_A_MATCH_MESSAGE for p in error_payloads)
    assert not any(p.get("type") == "game_state" for p in payloads)
    assert connection.closed is False


def test_full_flow_rejects_click_on_opponents_color_and_accepts_own():
    """End-to-end through handle_connection (not just _run_match_loop):
    after being matched and colored, a click on the opponent's back rank
    gets an error and no selection; a click on the player's own back rank
    afterward succeeds and selects that piece."""
    bus = InMemoryEventBus()
    session_registry = SessionRegistry(bus)
    connection = FakeConnection()
    auth_service, user_repository = make_auth_service_and_repository()

    async def scenario():
        session_id = session_registry.create_session("alice", "bob")
        players = session_registry.get_players(session_id)
        alice_is_white = players.white_username == "alice"
        # Row 7 is white's back rank, row 0 is black's, on the standard
        # starting board SessionRegistry deals out.
        own_row, opponent_row = (7, 0) if alice_is_white else (0, 7)

        matchmaking_service = FakeMatchmakingService(
            MatchResult(matched=True, opponent_username="bob", session_id=session_id))

        task = asyncio.ensure_future(handle_connection(
            connection, bus, NullLogger(), auth_service, matchmaking_service,
            session_registry, user_repository))
        await connection.inbound.put(encode(RegisterCommand(username="alice", password="hunter2")))
        await connection.inbound.put(encode(PlayCommand()))
        await connection.inbound.put(encode(ClickCommand(x=0, y=opponent_row * settings.CELL_SIZE)))
        await asyncio.sleep(0.05)
        await connection.inbound.put(encode(ClickCommand(x=0, y=own_row * settings.CELL_SIZE)))
        await asyncio.sleep(0.05)
        await connection.inbound.put(None)
        await task

        return own_row

    own_row = run_async(scenario())

    payloads = [json.loads(raw) for raw in connection.outbound]
    error_payloads = [p for p in payloads if p.get("type") == "error"]
    game_state_payloads = [p for p in payloads if p.get("type") == "game_state"]

    assert any(p["message"] == "That's not your piece to move." for p in error_payloads)
    assert any(p.get("selected_cell") == [own_row, 0] for p in game_state_payloads)
