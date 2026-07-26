"""server/connection_handler.py

Bridges one Connection to a GameSession for the lifetime of that connection:
- outbound: events published on the session's bus topic are encoded and
  pushed to the socket.
- inbound: decoded socket messages are dispatched to the matching session
  method.
"""
from __future__ import annotations

import asyncio

from application.game_session import GameSession
from ports.event_bus import EventBus
from ports.transport import Connection, ConnectionClosed
from protocol.codec import DecodeError, decode, encode
from protocol.messages import ClickCommand, ErrorMessage, JumpCommand


async def handle_connection(connection: Connection, session: GameSession,
                             event_bus: EventBus, logger) -> None:
    loop = asyncio.get_event_loop()

    def _forward(event: object) -> None:
        loop.create_task(connection.send(encode(event)))

    subscription = event_bus.subscribe(f"session:{session.session_id}", _forward)

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
