"""application/rating_update_service.py

RatingUpdateService — event-driven ELO updates, decoupled from GameSession
and connection_handler.py entirely: it only ever observes GameStateEvent
broadcasts on a session's bus topic, the same way any other subscriber
would. server_app.py calls subscribe_to(session_id) once per session
SessionRegistry creates; this class has no special access to the session
or engine beyond what the bus already broadcasts to everyone.
"""
from __future__ import annotations

import asyncio

from application.rating_service import compute_new_ratings
from ports.event_bus import EventBus
from ports.user_repository import UserRepository
from protocol.messages import GameStateEvent


class RatingUpdateService:

    def __init__(self, event_bus: EventBus, user_repository: UserRepository,
                 session_registry, logger):
        self._event_bus = event_bus
        self._user_repository = user_repository
        self._session_registry = session_registry
        self._logger = logger
        self._handled_sessions: set = set()
        self._lock = asyncio.Lock()

    def subscribe_to(self, session_id: str) -> None:
        """Start watching one session's topic for its eventual game-over
        broadcast. Call once per session, right after it's created."""
        def _on_event(event: object) -> None:
            self._handle_event(session_id, event)

        self._event_bus.subscribe(f"session:{session_id}", _on_event)

    def _handle_event(self, session_id: str, event: object) -> None:
        if not isinstance(event, GameStateEvent):
            return
        if not event.game_over or event.winner is None:
            return
        # Fast-path idempotency check: only one event with game_over=True
        # should ever fire per session today, but GameStateEvent is
        # broadcast to every subscriber — cheap insurance against a future
        # duplicate. This is NOT the authoritative guard (see
        # _apply_rating_update's re-check under the lock) — session_id is
        # only ever added to _handled_sessions once an update has actually
        # succeeded, so a session that failed here can still be retried by
        # a later duplicate event.
        if session_id in self._handled_sessions:
            return

        # Bus handlers are synchronous, but UserRepository's methods are
        # async (SqliteUserRepository offloads its actual I/O via
        # run_in_executor). Scheduling the persistence work as a task on the
        # running loop is safe here because this service only ever runs
        # inside the server's single asyncio event loop — same reasoning as
        # server/connection_handler.py's outbound writer task.
        asyncio.create_task(self._apply_rating_update(session_id, event.winner))

    async def _apply_rating_update(self, session_id: str, winner: str) -> None:
        async with self._lock:
            # Re-check under the lock: two duplicate events published
            # back-to-back with no yield in between can both pass
            # _handle_event's fast-path check before either of them gets
            # here — this second check, serialized by the lock, is the real,
            # race-proof guard against a double update.
            if session_id in self._handled_sessions:
                return

            try:
                players = self._session_registry.get_players(session_id)
                white_user = await self._user_repository.find_by_username(players.white_username)
                black_user = await self._user_repository.find_by_username(players.black_username)

                new_white_rating, new_black_rating = compute_new_ratings(
                    white_rating=white_user.rating, black_rating=black_user.rating, winner=winner,
                )

                await self._user_repository.update_rating(players.white_username, new_white_rating)
                await self._user_repository.update_rating(players.black_username, new_black_rating)
            except Exception:
                # This runs inside an untracked asyncio.create_task —
                # logging here IS the error handling; re-raising past this
                # point would just become another silently-dropped "Task
                # exception was never retrieved". session_id is deliberately
                # NOT added to _handled_sessions: a future duplicate
                # GameStateEvent (or a manual retry) gets a real second
                # attempt instead of being silently swallowed by the guard.
                self._logger.exception(
                    "Rating update failed for session %s (winner: %s)", session_id, winner)
                return

            self._handled_sessions.add(session_id)
            self._logger.info(
                "Rating update for session %s (winner: %s): %s %d -> %d, %s %d -> %d",
                session_id, winner,
                players.white_username, white_user.rating, new_white_rating,
                players.black_username, black_user.rating, new_black_rating,
            )
