"""server/connection_handler.py

Bridges one Connection to a GameSession for the lifetime of that connection:
- handshake: the connection must authenticate (via RegisterCommand or
  LoginCommand, delegated to AuthService) before anything else happens.
- outbound: events published on the session's bus topic are encoded and
  pushed to the socket.
- inbound: decoded socket messages are dispatched to the matching session
  method.
"""
from __future__ import annotations

import asyncio

from application.auth_service import AuthService
from application.game_session import GameSession
from ports.event_bus import EventBus
from ports.transport import Connection, ConnectionClosed
from protocol.codec import DecodeError, decode, encode
from protocol.messages import ClickCommand, ErrorMessage, JumpCommand, LoginCommand, RegisterCommand

_AUTH_REQUIRED_MESSAGE = "Authentication required: please log in or register first."


async def _authenticate(connection: Connection, auth_service: AuthService, logger) -> str | None:
    """Handshake loop: keep receiving messages until either a successful
    RegisterCommand or LoginCommand authenticates the connection.

    Unlike B1's username-only gate, auth failures and unrecognized messages
    during the handshake do NOT close the connection — they get an
    ErrorMessage and another chance to retry (a typo'd password, or a
    ClickCommand sent too early, shouldn't force a reconnect). Only
    ConnectionClosed ends the loop early, returning None.
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


async def _try_send(connection: Connection, message: object) -> bool:
    """Send a handshake-time reply, tolerating a connection that already
    closed. Returns False (caller should give up) if the send failed."""
    try:
        await connection.send(encode(message))
        return True
    except ConnectionClosed:
        return False


async def handle_connection(connection: Connection, session: GameSession,
                             event_bus: EventBus, logger, auth_service: AuthService) -> None:
    username = await _authenticate(connection, auth_service, logger)
    if username is None:
        return

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
                await connection.send(encode(ErrorMessage(message=str(exc))))
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
