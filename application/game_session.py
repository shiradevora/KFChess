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

    def handle_click(self, x: int, y: int) -> None:
        try:
            self._engine.dispatch_click(x, y)
        except GameOverError as exc:
            self._event_bus.publish(self._topic, ErrorMessage(message=str(exc)))
        self._publish_state()

    def handle_jump(self, x: int, y: int) -> None:
        try:
            self._engine.dispatch_jump(x, y)
        except GameOverError as exc:
            self._event_bus.publish(self._topic, ErrorMessage(message=str(exc)))
        self._publish_state()

    def tick(self, delta_ms: float) -> None:
        self._engine.update(delta_ms)
        self._publish_state()

    def _publish_state(self) -> None:
        snapshot = self._engine.get_state()
        event = snapshot_to_event(snapshot)
        self._event_bus.publish(self._topic, event)
