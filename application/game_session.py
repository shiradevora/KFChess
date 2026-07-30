"""application/game_session.py

GameSession — the application-layer façade around a single GameEngine.

Only accepts primitive click/jump coordinates in, only publishes
GameStateEvent (or ErrorMessage) out via the EventBus. Never exposes
GameStateSnapshot or any other domain object through its public API.
"""
from __future__ import annotations

from game.engine import GameEngine
from game.exceptions import GameOverError
from ports.event_bus import EventBus
from protocol.mapper import snapshot_to_event
from protocol.messages import ErrorMessage


class GameSession:

    def __init__(self, session_id: str, engine: GameEngine, event_bus: EventBus):
        self._session_id = session_id
        self._engine      = engine
        self._event_bus   = event_bus
        self._topic       = f"session:{session_id}"

    @property
    def session_id(self) -> str:
        return self._session_id

    def handle_click(self, x: int, y: int, acting_color: str) -> None:
        # The piece about to be acted on is whatever's already selected (a
        # move/toggle/reselect), or whatever sits at the clicked cell if
        # nothing is selected yet (a fresh select). Either way, checking
        # ONLY the color of that source piece — never the destination
        # cell's contents — is what's being enforced here: "which
        # connection may initiate this action at all", not "is this a
        # legal destination", which stays entirely the engine/rules'
        # job, unchanged.
        source_cell = self._engine.selected
        if source_cell is None:
            source_cell = self._engine.cell_at(x, y)
        if self._reject_if_wrong_color(source_cell, acting_color):
            return

        try:
            self._engine.dispatch_click(x, y)
        except GameOverError as exc:
            self._event_bus.publish(self._topic, ErrorMessage(message=str(exc)))
        self._publish_state()

    def handle_jump(self, x: int, y: int, acting_color: str) -> None:
        source_cell = self._engine.cell_at(x, y)
        if self._reject_if_wrong_color(source_cell, acting_color):
            return

        try:
            self._engine.dispatch_jump(x, y)
        except GameOverError as exc:
            self._event_bus.publish(self._topic, ErrorMessage(message=str(exc)))
        self._publish_state()

    def _reject_if_wrong_color(self, source_cell: tuple | None, acting_color: str) -> bool:
        """True (and publishes an ErrorMessage) if source_cell holds a piece
        that isn't acting_color's — the action must be dropped entirely
        without touching engine state. An empty source_cell isn't rejected
        here; the engine's existing click/jump handling already treats an
        empty-cell action as a no-op."""
        if source_cell is None:
            return False
        color = self._engine.color_at(*source_cell)
        if color is not None and color != acting_color:
            self._event_bus.publish(self._topic, ErrorMessage(
                message="That's not your piece to move."))
            return True
        return False

    def tick(self, delta_ms: float) -> None:
        self._engine.update(delta_ms)
        self._publish_state()

    def _publish_state(self) -> None:
        snapshot = self._engine.get_state()
        event = snapshot_to_event(snapshot)
        self._event_bus.publish(self._topic, event)
