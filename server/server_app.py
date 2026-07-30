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
from application.rating_update_service import RatingUpdateService
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

    # One shared UserRepository + AuthService for the whole server process —
    # not one per connection. ensure_schema() only needs to run once, before
    # any connection can authenticate against it.
    user_repository = SqliteUserRepository(settings.DB_PATH)
    await user_repository.ensure_schema()
    auth_service = AuthService(user_repository)

    # RatingUpdateService is wired independently of SessionRegistry/
    # GameSession: it only ever watches a session's topic like any other
    # subscriber, via subscribe_to(). Composing that call into the
    # session_factory below (rather than teaching SessionRegistry about
    # rating updates) keeps SessionRegistry's responsibilities limited to
    # session/ticker/player-mapping lifecycle, nothing else.
    rating_update_service = RatingUpdateService(bus, user_repository, session_registry, logger)

    def _create_session_and_subscribe(user_a: str, user_b: str) -> str:
        session_id = session_registry.create_session(user_a, user_b)
        rating_update_service.subscribe_to(session_id)
        return session_id

    # Stage C2: session creation now needs both usernames too, to assign
    # colors (SessionRegistry.create_session randomly assigns one to white,
    # one to black) — game logic itself still stays unaware of usernames
    # (GameSession only ever sees colors), but SessionRegistry, which owns
    # session creation, is the natural place to hold the session_id ->
    # players mapping.
    matchmaking_service = MatchmakingService(session_factory=_create_session_and_subscribe)

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
