"""server/connection_handler.py

Bridges one Connection to a matched GameSession for the lifetime of that
connection, in three phases:
- handshake: the connection must authenticate (via RegisterCommand or
  LoginCommand, delegated to AuthService) before anything else happens.
- lobby: once authenticated, the connection waits for a PlayCommand and
  gets matched (via MatchmakingService) to another waiting player. There is
  no default session — a connection only joins one once matched.
- match: after a successful match, outbound events published on the
  session's bus topic are encoded and pushed to the socket; inbound
  click/jump commands are dispatched to the session.
"""
from __future__ import annotations

import asyncio

from application.auth_service import AuthService
from application.game_session import GameSession
from application.matchmaking_service import MatchmakingService
from ports.event_bus import EventBus
from ports.transport import Connection, ConnectionClosed
from ports.user_repository import UserRepository
from protocol.codec import DecodeError, decode, encode
from protocol.messages import (
    AuthSuccessEvent,
    ClickCommand,
    ErrorMessage,
    JumpCommand,
    LoginCommand,
    MatchFoundEvent,
    PlayCommand,
    RegisterCommand,
)
from server.session_registry import SessionRegistry

_AUTH_REQUIRED_MESSAGE = "Authentication required: please log in or register first."
_NOT_IN_A_MATCH_MESSAGE = "Not in a match yet — type 'play' to find an opponent."
_NO_OPPONENT_FOUND_MESSAGE = "No opponent found — please try 'play' again."


async def _try_send(connection: Connection, message: object) -> bool:
    """Send a reply, tolerating a connection that already closed. Returns
    False (caller should give up) if the send failed."""
    try:
        await connection.send(encode(message))
        return True
    except ConnectionClosed:
        return False


async def _authenticate(connection: Connection, auth_service: AuthService, logger) -> str | None:
    """Handshake loop: keep receiving messages until either a successful
    RegisterCommand or LoginCommand authenticates the connection.

    Auth failures and unrecognized messages during the handshake do NOT
    close the connection — they get an ErrorMessage and another chance to
    retry (a typo'd password, or a ClickCommand sent too early, shouldn't
    force a reconnect). Only ConnectionClosed ends the loop early,
    returning None.
    """
    while True:
        try:
            raw = await connection.receive()
        except ConnectionClosed:
            return None

        try:
            message = decode(raw)
        except DecodeError as exc:
            logger.warning("Malformed message during handshake from %s: %s",
                            connection.connection_id, exc)
            if not await _try_send(connection, ErrorMessage(message=_AUTH_REQUIRED_MESSAGE)):
                return None
            continue

        if isinstance(message, RegisterCommand):
            result = await auth_service.register(message.username, message.password)
            if not result.success:
                logger.info("Registration failed for %r (connection %s): %s",
                            message.username, connection.connection_id, result.error)
                if not await _try_send(connection, ErrorMessage(message=result.error)):
                    return None
                continue
            logger.info("Player registered and logged in: %s (connection %s)",
                         message.username, connection.connection_id)
            return message.username

        if isinstance(message, LoginCommand):
            result = await auth_service.login(message.username, message.password)
            if not result.success:
                # AuthService.login() intentionally collapses "unknown
                # username" and "wrong password" into a single generic
                # result (username-enumeration mitigation) — there is no
                # separate reason available here to log distinctly, so this
                # log line stays as generic as the client-facing message.
                logger.info("Login failed for %r (connection %s)",
                            message.username, connection.connection_id)
                if not await _try_send(connection, ErrorMessage(message=result.error)):
                    return None
                continue
            logger.info("Player logged in: %s (connection %s)",
                         message.username, connection.connection_id)
            return message.username

        logger.warning("Connection %s sent %s before authenticating",
                        connection.connection_id, type(message).__name__)
        if not await _try_send(connection, ErrorMessage(message=_AUTH_REQUIRED_MESSAGE)):
            return None


async def _lobby(connection: Connection, username: str, logger,
                  matchmaking_service: MatchmakingService,
                  session_registry: SessionRegistry,
                  user_repository: UserRepository) -> GameSession | None:
    """Wait for a PlayCommand and get matched. Click/jump (or anything else
    that isn't a PlayCommand) sent while still in the lobby gets an
    ErrorMessage, not a crash — the connection stays in the lobby loop so
    the player can still type 'play'. Returns the matched GameSession, or
    None if the connection closed before a match was made.
    """
    while True:
        try:
            raw = await connection.receive()
        except ConnectionClosed:
            return None

        try:
            message = decode(raw)
        except DecodeError as exc:
            logger.warning("Malformed message in lobby from %s: %s", connection.connection_id, exc)
            if not await _try_send(connection, ErrorMessage(message=_NOT_IN_A_MATCH_MESSAGE)):
                return None
            continue

        if isinstance(message, PlayCommand):
            user = await user_repository.find_by_username(username)
            result = await matchmaking_service.enqueue_and_wait(username, user.rating)

            if not result.matched:
                logger.info("No match found for %s (connection %s)",
                            username, connection.connection_id)
                if not await _try_send(connection, ErrorMessage(message=_NO_OPPONENT_FOUND_MESSAGE)):
                    return None
                continue

            logger.info("Match found: %s vs %s (session %s)",
                         username, result.opponent_username, result.session_id)
            if not await _try_send(connection, MatchFoundEvent(
                    opponent_username=result.opponent_username, session_id=result.session_id)):
                return None

            return session_registry.get_session(result.session_id)

        logger.warning("Connection %s sent %s while in the lobby",
                        connection.connection_id, type(message).__name__)
        if not await _try_send(connection, ErrorMessage(message=_NOT_IN_A_MATCH_MESSAGE)):
            return None


async def _run_match_loop(connection: Connection, session: GameSession,
                           event_bus: EventBus, logger) -> None:
    """Bridge a connection to its matched GameSession for the rest of the
    connection's lifetime: outbound events on the session's bus topic are
    forwarded to the socket; inbound click/jump commands are dispatched to
    the session. Extracted so both the matchmaking-driven path in
    handle_connection() and tests that only care about this mechanic (not
    authentication or matchmaking) can call it directly with a
    directly-constructed session.
    """
    outbox: asyncio.Queue = asyncio.Queue()

    def _forward(event: object) -> None:
        outbox.put_nowait(encode(event))

    subscription = event_bus.subscribe(f"session:{session.session_id}", _forward)

    async def _writer() -> None:
        # A single dedicated writer per connection: sends drain the outbox
        # one at a time, so we never have two concurrent send() calls racing
        # on the same underlying connection.
        while True:
            raw = await outbox.get()
            try:
                await connection.send(raw)
            except ConnectionClosed:
                return

    writer_task = asyncio.create_task(_writer())

    try:
        while True:
            try:
                raw = await connection.receive()
            except ConnectionClosed:
                return

            try:
                message = decode(raw)
            except DecodeError as exc:
                logger.warning("Malformed message from %s: %s", connection.connection_id, exc)
                outbox.put_nowait(encode(ErrorMessage(message=str(exc))))
                continue

            if isinstance(message, ClickCommand):
                session.handle_click(message.x, message.y)
            elif isinstance(message, JumpCommand):
                session.handle_jump(message.x, message.y)
    finally:
        subscription.unsubscribe()
        writer_task.cancel()
        try:
            await writer_task
        except asyncio.CancelledError:
            pass


async def handle_connection(connection: Connection, event_bus: EventBus, logger,
                             auth_service: AuthService,
                             matchmaking_service: MatchmakingService,
                             session_registry: SessionRegistry,
                             user_repository: UserRepository) -> None:
    username = await _authenticate(connection, auth_service, logger)
    if username is None:
        return

    if not await _try_send(connection, AuthSuccessEvent(username=username)):
        return

    session = await _lobby(connection, username, logger, matchmaking_service,
                            session_registry, user_repository)
    if session is None:
        return

    await _run_match_loop(connection, session, event_bus, logger)
