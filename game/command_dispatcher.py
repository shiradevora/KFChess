"""game/command_dispatcher.py

CommandDispatcher — the boundary between the Controller and the Engine.

Responsibilities
----------------
* Own the "currently selected cell" UI state (which cell the player
  has highlighted but not yet acted on).
* Translate raw pixel coordinates into logical (row, col) board cells.
* Decide which domain command (SelectCommand, MoveCommand, JumpCommand)
  a click or jump action corresponds to.
* Dispatch the resulting command to the GameEngine.

What this class does NOT do
---------------------------
* No rendering or visual feedback.
* No game-rule validation (that is the engine's job).
* No network I/O.

Naming rationale
----------------
The old class was called "InputHandler", which implied it handled
hardware input.  In reality it translated logical board actions into
engine calls — that is a dispatcher / translator role, not an input
role.  The GUI layer (gui/app.py) is the true input handler; it
converts raw OpenCV mouse events into calls on this class.
"""
from __future__ import annotations

from game.commands import MoveCommand, JumpCommand, SelectCommand
from game.exceptions import InvalidMoveError
from game.models import Move, Jump
from rules.movement_strategy import MoveContext


class CommandDispatcher:

    def __init__(self, board, registry, resolver, config):
        self._board    = board
        self._registry = registry
        self._resolver = resolver
        self._config   = config
        self._selected: tuple | None = None

    # ------------------------------------------------------------------
    # Public read-only state
    # ------------------------------------------------------------------

    @property
    def selected(self) -> tuple | None:
        return self._selected

    # ------------------------------------------------------------------
    # Public dispatch methods (called by the Controller / GUI)
    # ------------------------------------------------------------------

    def dispatch_click(self, x: int, y: int, clock_ms: float) -> None:
        """Translate a pixel click into a Select or Move command."""
        cell = self._pixel_to_cell(x, y)
        if cell is None:
            return

        if self._selected is None:
            self._execute_select(SelectCommand(cell))
        else:
            self._execute_action(cell, clock_ms)

    def dispatch_jump(self, x: int, y: int, clock_ms: float) -> None:
        """Translate a pixel right-click into a Jump command."""
        self._selected = None
        cell = self._pixel_to_cell(x, y)
        if cell is None:
            return
        self._execute_jump(JumpCommand(cell), clock_ms)

    # ------------------------------------------------------------------
    # Command execution
    # ------------------------------------------------------------------

    def _execute_select(self, cmd: SelectCommand) -> None:
        cell = cmd.cell
        if cell is None or self._resolver.is_busy(cell):
            self._selected = None
            return
        token = self._board.get(*cell)
        self._selected = cell if token != self._config.EMPTY_CELL else None

    def _execute_jump(self, cmd: JumpCommand, clock_ms: float) -> None:
        cell = cmd.cell
        if self._resolver.is_busy(cell):
            return
        piece = self._board.get(*cell)
        if piece == self._config.EMPTY_CELL:
            return
        self._resolver.add_jump(
            Jump(piece, cell, clock_ms + self._config.JUMP_DURATION)
        )

    def _execute_action(self, end: tuple, clock_ms: float) -> None:
        """Resolve what happens when the player clicks *end* with a piece selected."""
        start = self._selected

        # Toggle off — clicking the already-selected cell deselects
        if end == start:
            self._selected = None
            return

        piece = self._board.get(*start)

        # Selected piece has since moved away or is in transit — clear
        if piece == self._config.EMPTY_CELL or self._resolver.is_busy(start):
            self._selected = None
            return

        target = self._board.get(*end)

        # Friendly piece — switch selection (if not busy)
        if target != self._config.EMPTY_CELL and target[0] == piece[0]:
            if not self._resolver.is_busy(end):
                self._selected = end
            return

        # Attempt move — raises InvalidMoveError if illegal
        self._execute_move(MoveCommand(start=start, end=end), piece, target, clock_ms)

    def _execute_move(self, cmd: MoveCommand,
                      piece: str, target: str, clock_ms: float) -> None:
        if not self._is_legal(piece, cmd.start, cmd.end):
            # Illegal move onto empty square → deselect
            # Illegal capture → keep selection (player may try another target)
            if target == self._config.EMPTY_CELL:
                self._selected = None
            raise InvalidMoveError(piece, cmd.start, cmd.end, "movement rule violation")

        self._board.set(*cmd.start, self._config.EMPTY_CELL)
        duration = self._config.move_duration(cmd.start, cmd.end)
        self._resolver.add_move(Move(
            piece       = piece,
            start       = cmd.start,
            end         = cmd.end,
            dispatch_ms = clock_ms,
            arrival     = clock_ms + duration,
        ))
        self._selected = None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _pixel_to_cell(self, x: int, y: int) -> tuple | None:
        row = y // self._config.CELL_SIZE
        col = x // self._config.CELL_SIZE
        if not self._board.in_bounds(row, col):
            return None
        return row, col

    def _is_legal(self, piece: str, start: tuple, end: tuple) -> bool:
        from rules.piece_type import PieceType
        strategy = self._registry.get(PieceType.from_token(piece[1]))
        dr = end[0] - start[0]
        dc = end[1] - start[1]
        context = MoveContext(
            board           = self._board,
            color           = piece[0],
            start           = start,
            end             = end,
            target_occupied = not self._board.is_empty(*end),
        )
        return strategy.is_legal(dr, dc, context)
