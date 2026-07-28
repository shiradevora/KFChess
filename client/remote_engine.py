"""client/remote_engine.py

RemoteGameEngine — adapter that lets gui/app.py's App treat a remote server
exactly like a local GameEngine. Read-only state comes from the latest
GameStateEvent received from the server; commands are forwarded to the
server (via a ServerGateway) instead of being applied locally.
"""
from __future__ import annotations

import logging
import threading
import time

from ports.event_bus import EventBus
from ports.game_engine_port import GameEnginePort
from protocol.messages import ErrorMessage, GameStateEvent

SERVER_EVENTS_TOPIC = "server_events"
_POLL_INTERVAL_S = 0.02


class RemoteGameEngine(GameEnginePort):
    """Implements GameEnginePort — the read-only state and command-dispatch
    interface gui/app.py's App depends on: .clock, .snapshot(),
    .active_moves, .active_jumps, .selected, .game_over, .board_width,
    .board_height, .handle_click(x, y), .handle_jump(x, y).

    Deliberately does NOT implement SelfTicking/.wait(): the clock is owned
    by the server, not this adapter — state only advances when a new
    GameStateEvent is received.
    """

    def __init__(self, gateway, event_bus: EventBus,
                 initial_state_timeout_s: float = 5.0, logger=None):
        self._gateway = gateway
        self._logger = logger or logging.getLogger(__name__)
        self._lock = threading.Lock()
        self._latest_state: GameStateEvent | None = None

        def _on_event(event: object) -> None:
            if isinstance(event, GameStateEvent):
                with self._lock:
                    self._latest_state = event
            elif isinstance(event, ErrorMessage):
                self._logger.warning("Server rejected a command: %s", event.message)

        event_bus.subscribe(SERVER_EVENTS_TOPIC, _on_event)

        deadline = time.monotonic() + initial_state_timeout_s
        while not self._has_state():
            if time.monotonic() >= deadline:
                raise ConnectionError(
                    f"No game state received from the server within "
                    f"{initial_state_timeout_s}s — is server_app.py running and reachable?"
                )
            time.sleep(_POLL_INTERVAL_S)

    def _has_state(self) -> bool:
        with self._lock:
            return self._latest_state is not None

    # ------------------------------------------------------------------
    # Duck-typed read-only state
    # ------------------------------------------------------------------

    @property
    def clock(self) -> float:
        with self._lock:
            return self._latest_state.clock_ms

    def snapshot(self) -> list:
        with self._lock:
            board_tokens = self._latest_state.board_tokens
        return [list(row) for row in board_tokens]

    @property
    def active_moves(self) -> tuple:
        with self._lock:
            return self._latest_state.active_moves

    @property
    def active_jumps(self) -> tuple:
        with self._lock:
            return self._latest_state.active_jumps

    @property
    def selected(self):
        with self._lock:
            return self._latest_state.selected_cell

    @property
    def game_over(self) -> bool:
        with self._lock:
            return self._latest_state.game_over

    @property
    def board_width(self) -> int:
        with self._lock:
            return self._latest_state.board_width

    @property
    def board_height(self) -> int:
        with self._lock:
            return self._latest_state.board_height

    # ------------------------------------------------------------------
    # Commands — forwarded to the server, never applied locally
    # ------------------------------------------------------------------

    def handle_click(self, x: int, y: int) -> None:
        self._gateway.send_click(x, y)

    def handle_jump(self, x: int, y: int) -> None:
        self._gateway.send_jump(x, y)
