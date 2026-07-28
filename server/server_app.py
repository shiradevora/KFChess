"""server/server_app.py

Composition root for the WebSocket server. Board/registry/win_condition/
promotion_rule/engine wiring mirrors main.py and main_gui.py exactly
(same GameEngine(board=..., rule_registry=..., win_condition=...,
promotion_rule=..., config=...) call); the board itself uses the standard
starting position from main_gui.py since this entry point has no stdin
board input to parse.
"""
from __future__ import annotations

import asyncio
import logging

from board.text_board import TextBoardRepresentation
from config import settings
from rules.game_conditions import KingCaptureWinCondition, LastRankPromotion
from rules.rule_registry import build_default_registry
from game.engine import GameEngine
from application.auth_service import AuthService
from application.game_session import GameSession
from infrastructure.bus.in_memory_bus import InMemoryEventBus
from infrastructure.persistence.sqlite_user_repository import SqliteUserRepository
from infrastructure.websocket.ws_transport import WebSocketTransportServer
from server.connection_handler import handle_connection

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("kungfu_chess.server")

_STARTING_BOARD = [
    "bR bN bB bQ bK bB bN bR".split(),
    "bP bP bP bP bP bP bP bP".split(),
    ". . . . . . . .".split(),
    ". . . . . . . .".split(),
    ". . . . . . . .".split(),
    ". . . . . . . .".split(),
    "wP wP wP wP wP wP wP wP".split(),
    "wR wN wB wQ wK wB wN wR".split(),
]


def _build_session() -> tuple:
    """Build the single global GameSession used by the entire server process.

    PLACEHOLDER for this development stage (network plumbing only): every
    connecting client joins this one shared session. There is no player
    pairing, matchmaking, or per-match session lifecycle yet — all
    connections interact with the same board and the same engine state.
    This is intentional for now. Once matchmaking is implemented, this
    function will be replaced by a MatchmakingService that creates a fresh
    GameSession (with its own ticker, per _run_ticker) for each matched
    pair of players.
    """
    board = TextBoardRepresentation(_STARTING_BOARD, empty_token=settings.EMPTY_CELL)
    engine = GameEngine(
        board=board,
        rule_registry=build_default_registry(settings),
        win_condition=KingCaptureWinCondition(),
        promotion_rule=LastRankPromotion(),
        config=settings,
    )
    bus = InMemoryEventBus()
    session = GameSession(session_id="default", engine=engine, event_bus=bus)
    return session, bus


async def _run_ticker(session: GameSession) -> None:
    while True:
        await asyncio.sleep(settings.SERVER_TICK_MS / 1000)
        session.tick(settings.SERVER_TICK_MS)


async def run() -> None:
    # NOTE: creates ONE global session/ticker for ALL clients that ever
    # connect to this server process, regardless of how many players are
    # connected (including zero). This is a deliberate placeholder for the
    # current stage; see _build_session() docstring. In a future step this
    # will be replaced by per-match session creation driven by a
    # MatchmakingService, once a pair of players is matched.
    session, bus = _build_session()

    # One shared UserRepository + AuthService for the whole server process —
    # not one per connection. ensure_schema() only needs to run once, before
    # any connection can authenticate against it.
    user_repository = SqliteUserRepository(settings.DB_PATH)
    await user_repository.ensure_schema()
    auth_service = AuthService(user_repository)

    transport = WebSocketTransportServer(settings.WS_HOST, settings.WS_PORT)

    async def on_connect(connection):
        await handle_connection(connection, session, bus, logger, auth_service)

    await transport.start(on_connect=on_connect)
    logger.info("WebSocket server listening on ws://%s:%s", settings.WS_HOST, settings.WS_PORT)

    await _run_ticker(session)


if __name__ == "__main__":
    asyncio.run(run())
