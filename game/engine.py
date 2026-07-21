"""game/engine.py

GameEngine — the domain core of KungFu Chess.

Responsibilities
----------------
* Own the game clock.
* Drive MoveResolver.update(delta_ms) each tick.
* Accept domain commands via dispatch_click / dispatch_jump
  (delegated to CommandDispatcher).
* Expose the complete game state as a single immutable
  GameStateSnapshot via get_state().
* Raise GameOverError when commands arrive after the game has ended.

What this class does NOT do
---------------------------
* No pixel / screen-space knowledge.
* No rendering.
* No asset loading.

Backwards-compatibility shims
------------------------------
The public methods wait(), handle_click(), handle_jump(), selected,
board_height, board_width, snapshot(), active_moves, active_jumps, and
render() are thin wrappers kept so that all existing tests and the
text-mode main.py continue to work without modification.
"""
from __future__ import annotations

from game.command_dispatcher import CommandDispatcher
from game.exceptions import GameOverError, InvalidMoveError
from game.move_resolver import MoveResolver
from game.state_snapshot import GameStateSnapshot


class GameEngine:

    def __init__(self, board, rule_registry, win_condition, promotion_rule, config):
        self._board      = board
        self._config     = config
        self._resolver   = MoveResolver(board, win_condition, promotion_rule, config)
        self._dispatcher = CommandDispatcher(
            board, rule_registry, self._resolver, config
        )

    # ------------------------------------------------------------------
    # Primary public API
    # ------------------------------------------------------------------

    def update(self, delta_ms: float) -> None:
        """Advance the game clock and settle any arrived moves."""
        self._resolver.update(delta_ms)

    def get_state(self) -> GameStateSnapshot:
        """Return a complete, immutable snapshot of the current game state."""
        raw = self._board.snapshot()
        return GameStateSnapshot(
            clock_ms      = self._resolver.clock_ms,
            board_tokens  = tuple(tuple(row) for row in raw),
            board_height  = self._board.height,
            board_width   = self._board.width,
            active_moves  = self._resolver.active_moves,
            active_jumps  = self._resolver.active_jumps,
            selected_cell = self._dispatcher.selected,
            game_over     = self._resolver.game_over,
            empty_token   = self._config.EMPTY_CELL,
        )

    def dispatch_click(self, x: int, y: int) -> None:
        """Translate a pixel click and dispatch the resulting command."""
        if self._resolver.game_over:
            raise GameOverError()
        self._resolver.update(0)
        try:
            self._dispatcher.dispatch_click(x, y, self._resolver.clock_ms)
        except InvalidMoveError:
            pass  # selection state already updated by dispatcher; caller may log

    def dispatch_jump(self, x: int, y: int) -> None:
        """Translate a pixel right-click and dispatch the resulting command."""
        if self._resolver.game_over:
            raise GameOverError()
        self._resolver.update(0)
        self._dispatcher.dispatch_jump(x, y, self._resolver.clock_ms)

    # ------------------------------------------------------------------
    # Backwards-compatibility shims (used by existing tests + main.py)
    # ------------------------------------------------------------------

    @property
    def game_over(self) -> bool:
        return self._resolver.game_over

    @property
    def clock(self) -> float:
        return self._resolver.clock_ms

    @property
    def selected(self) -> tuple | None:
        return self._dispatcher.selected

    @property
    def active_moves(self) -> tuple:
        return self._resolver.active_moves

    @property
    def active_jumps(self) -> tuple:
        return self._resolver.active_jumps

    @property
    def board_height(self) -> int:
        return self._board.height

    @property
    def board_width(self) -> int:
        return self._board.width

    def snapshot(self) -> list[list[str]]:
        return self._board.snapshot()

    def wait(self, dt: float) -> None:
        self._resolver.update(dt)

    def handle_click(self, x: int, y: int) -> None:
        if self._resolver.game_over:
            return
        self._resolver.update(0)
        try:
            self._dispatcher.dispatch_click(x, y, self._resolver.clock_ms)
        except InvalidMoveError:
            pass

    def handle_jump(self, x: int, y: int) -> None:
        if self._resolver.game_over:
            return
        self._resolver.update(0)
        self._dispatcher.dispatch_jump(x, y, self._resolver.clock_ms)

    def render(self, renderer) -> str:
        self._resolver.update(0)
        return renderer.render(self._board)
