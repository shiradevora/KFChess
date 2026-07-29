"""server/server_app.py

Composition root for the WebSocket server.

Stage C1 replaces the single global GameSession + ticker (a deliberate
placeholder for earlier stages, when there was no matchmaking) with real
per-match sessions: SessionRegistry creates a fresh GameSession (with its
own ticker task) only once MatchmakingService pairs two players. There is
no default session anymore — a connection only ever joins a session by
being matched.
"""
from __future__ import annotations

import asyncio
import logging

from config import settings
from application.auth_service import AuthService
from application.matchmaking_service import MatchmakingService
from infrastructure.bus.in_memory_bus import InMemoryEventBus
from infrastructure.persistence.sqlite_user_repository import SqliteUserRepository
from infrastructure.websocket.ws_transport import WebSocketTransportServer
from server.connection_handler import handle_connection
from server.session_registry import SessionRegistry

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("kungfu_chess.server")


async def run() -> None:
    bus = InMemoryEventBus()
    session_registry = SessionRegistry(bus)

    # session_factory ignores the two usernames it's given: session/engine
    # creation itself doesn't need to know who's playing (game logic stays
    # unaware of usernames, same as every earlier stage) — only
    # MatchmakingService needs the usernames, to report each player's
    # opponent back to them.
    matchmaking_service = MatchmakingService(
        session_factory=lambda user_a, user_b: session_registry.create_session(),
    )

    # One shared UserRepository + AuthService for the whole server process —
    # not one per connection. ensure_schema() only needs to run once, before
    # any connection can authenticate against it.
    user_repository = SqliteUserRepository(settings.DB_PATH)
    await user_repository.ensure_schema()
    auth_service = AuthService(user_repository)

    transport = WebSocketTransportServer(settings.WS_HOST, settings.WS_PORT)

    async def on_connect(connection):
        await handle_connection(
            connection, bus, logger, auth_service,
            matchmaking_service, session_registry, user_repository,
        )

    await transport.start(on_connect=on_connect)
    logger.info("WebSocket server listening on ws://%s:%s", settings.WS_HOST, settings.WS_PORT)

    # Nothing left to await forever on here: each match now drives its own
    # ticker task (started by SessionRegistry.create_session), not a single
    # process-wide ticker. Block forever so the process stays up to accept
    # connections.
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(run())
