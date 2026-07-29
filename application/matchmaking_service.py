"""application/matchmaking_service.py

MatchmakingService — owns the queue of players waiting for a match and
pairs them by rating. Runs entirely inside the asyncio event loop:
concurrent connection handlers call enqueue_and_wait() as coroutines, never
as separate threads, so the queue is protected with asyncio.Lock (not
threading.Lock — there's no separate thread here, just concurrent
coroutines interleaving at await points).

session_factory is injected (not hardcoded to GameEngine/GameSession
construction) so this service stays testable without real game engines —
production wires it to SessionRegistry.create_session; tests can pass a
fake that returns a dummy session_id.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Callable, List, Optional


@dataclass(frozen=True)
class MatchResult:
    matched: bool
    opponent_username: Optional[str]
    session_id: Optional[str]


@dataclass(eq=False)
class _WaitingPlayer:
    """Mutable per-call record tracked in the queue. eq=False forces
    identity-based comparison (list membership/removal), since `result` is
    mutated in place by whichever caller ends up pairing this player."""
    username: str
    rating: int
    event: asyncio.Event
    result: Optional[MatchResult] = field(default=None)


class MatchmakingService:
    """Owns the queue of players waiting for a match."""

    def __init__(self, session_factory: Callable[[str, str], str],
                 rating_tolerance: int = 100, timeout_s: float = 60.0):
        self._session_factory = session_factory
        self._rating_tolerance = rating_tolerance
        self._timeout_s = timeout_s
        self._lock = asyncio.Lock()
        self._waiting: List[_WaitingPlayer] = []

    async def enqueue_and_wait(self, username: str, rating: int) -> MatchResult:
        waiting_player = _WaitingPlayer(username=username, rating=rating, event=asyncio.Event())

        async with self._lock:
            opponent = self._find_compatible_opponent(rating)
            if opponent is not None:
                # We are the SECOND arrival within tolerance: we notice the
                # match, create the session, and wake the first arrival
                # (who is asyncio-waiting below) with the result — the
                # first arrival never creates a session itself, so two
                # concurrent callers can't race to create two different
                # sessions for the same pair.
                self._waiting.remove(opponent)
                session_id = self._session_factory(opponent.username, username)
                opponent.result = MatchResult(
                    matched=True, opponent_username=username, session_id=session_id)
                opponent.event.set()
                return MatchResult(
                    matched=True, opponent_username=opponent.username, session_id=session_id)

            self._waiting.append(waiting_player)

        try:
            await asyncio.wait_for(waiting_player.event.wait(), timeout=self._timeout_s)
        except asyncio.TimeoutError:
            async with self._lock:
                if waiting_player in self._waiting:
                    self._waiting.remove(waiting_player)
                    return MatchResult(matched=False, opponent_username=None, session_id=None)
            # Rare race: a later arrival paired us in the instant between
            # our timeout firing and us acquiring the lock to dequeue
            # ourselves — the result it set is the real, valid match.
            return waiting_player.result

        return waiting_player.result

    def _find_compatible_opponent(self, rating: int) -> Optional[_WaitingPlayer]:
        for candidate in self._waiting:
            if abs(candidate.rating - rating) <= self._rating_tolerance:
                return candidate
        return None
