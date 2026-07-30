"""server/session_registry.py

SessionRegistry — creates and tracks per-match GameSessions, each with its
own ticker task. Replaces the single global session + ticker that used to
run for the whole server process regardless of how many players were
connected (see server_app.py's git history / stage B docs): sessions are now
created only when MatchmakingService pairs two players.

One shared EventBus for the whole server; sessions are distinguished purely
by topic (f"session:{session_id}"), exactly as before matchmaking existed —
this registry only adds session/ticker lifecycle management on top.
"""
from __future__ import annotations

import asyncio
import random
import uuid
from dataclasses import dataclass

from board.text_board import TextBoardRepresentation
from config import settings
from rules.game_conditions import KingCaptureWinCondition, LastRankPromotion
from rules.rule_registry import build_default_registry
from game.engine import GameEngine
from application.game_session import GameSession
from ports.event_bus import EventBus

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


@dataclass(frozen=True)
class SessionPlayers:
    """Which username is playing which color for one session — the mapping
    RatingUpdateService and connection_handler.py both need, but GameSession
    itself never sees (it only ever deals in colors, not usernames)."""
    white_username: str
    black_username: str


class SessionRegistry:
    """Owns every live GameSession and its per-session ticker task."""

    def __init__(self, event_bus: EventBus):
        self._event_bus = event_bus
        self._sessions: dict[str, GameSession] = {}
        self._ticker_tasks: dict[str, asyncio.Task] = {}
        self._players: dict[str, SessionPlayers] = {}

    def create_session(self, username_a: str, username_b: str) -> str:
        """Build a fresh GameEngine/GameSession (same construction as
        stage B's single global session) and start its own ticker task.
        Randomly assigns one of the two matched usernames to white and the
        other to black. Returns the new session_id."""
        session_id = str(uuid.uuid4())
        board = TextBoardRepresentation(_STARTING_BOARD, empty_token=settings.EMPTY_CELL)
        engine = GameEngine(
            board=board,
            rule_registry=build_default_registry(settings),
            win_condition=KingCaptureWinCondition(),
            promotion_rule=LastRankPromotion(),
            config=settings,
        )
        session = GameSession(session_id=session_id, engine=engine, event_bus=self._event_bus)

        if random.random() < 0.5:
            white_username, black_username = username_a, username_b
        else:
            white_username, black_username = username_b, username_a
        self._players[session_id] = SessionPlayers(
            white_username=white_username, black_username=black_username,
        )

        self._sessions[session_id] = session
        self._ticker_tasks[session_id] = asyncio.create_task(self._run_ticker(session))
        return session_id

    def get_session(self, session_id: str) -> GameSession:
        return self._sessions[session_id]

    def get_players(self, session_id: str) -> SessionPlayers:
        return self._players[session_id]

    def remove_session(self, session_id: str) -> None:
        """Cancel the session's ticker task and drop it from the registry.
        Not wired to anything yet at this stage — game-over cleanup is a
        later step's concern."""
        ticker_task = self._ticker_tasks.pop(session_id, None)
        if ticker_task is not None:
            ticker_task.cancel()
        self._sessions.pop(session_id, None)
        self._players.pop(session_id, None)

    async def _run_ticker(self, session: GameSession) -> None:
        while True:
            await asyncio.sleep(settings.SERVER_TICK_MS / 1000)
            session.tick(settings.SERVER_TICK_MS)
