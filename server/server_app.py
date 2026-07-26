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
from application.game_session import GameSession
from infrastructure.bus.in_memory_bus import InMemoryEventBus
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
    session, bus = _build_session()
    transport = WebSocketTransportServer(settings.WS_HOST, settings.WS_PORT)

    async def on_connect(connection):
        await handle_connection(connection, session, bus, logger)

    await transport.start(on_connect=on_connect)
    logger.info("WebSocket server listening on ws://%s:%s", settings.WS_HOST, settings.WS_PORT)

    await _run_ticker(session)


if __name__ == "__main__":
    asyncio.run(run())
