from game.models import Move, Jump
from rules.movement_strategy import MoveContext


class InputHandler:
    def __init__(self, board, registry, resolver, config):
        self._board = board
        self._registry = registry
        self._resolver = resolver
        self._config = config
        self._selected = None

    @property
    def selected(self):
        return self._selected

    def handle_click(self, x, y, clock):
        cell = self._pixel_to_cell(x, y)
        if cell is None:
            return

        if self._selected is None:
            self._selected = self._select(cell)
            return

        self._act_on_selection(cell, clock)

    def handle_jump(self, x, y, clock):
        self._selected = None
        cell = self._pixel_to_cell(x, y)
        if cell is None or self._resolver.is_busy(cell):
            return

        piece = self._board.get(*cell)
        if piece == self._config.EMPTY_CELL:
            return

        self._resolver.add_jump(Jump(piece, cell, clock + self._config.JUMP_DURATION))

    def _pixel_to_cell(self, x, y):
        row = y // self._config.CELL_SIZE
        col = x // self._config.CELL_SIZE
        if not self._board.in_bounds(row, col):
            return None
        return row, col

    def _select(self, cell):
        if self._resolver.is_busy(cell):
            return None
        return cell if self._board.get(*cell) != self._config.EMPTY_CELL else None

    def _act_on_selection(self, cell, clock):
        start = self._selected

        # Clicking the already-selected cell toggles selection off
        if cell == start:
            self._selected = None
            return

        piece = self._board.get(*start)

        # Selected piece has since moved away or is now in transit — clear
        if piece == self._config.EMPTY_CELL or self._resolver.is_busy(start):
            self._selected = None
            return

        target = self._board.get(*cell)

        # Clicking a friendly piece — switch selection to it (if not busy)
        if target != self._config.EMPTY_CELL and target[0] == piece[0]:
            if not self._resolver.is_busy(cell):
                self._selected = cell
            # If the friendly piece is busy, keep current selection unchanged
            return

        # Clicking an empty square or enemy piece — attempt the move
        if not self._is_legal_move(piece, start, cell):
            # Illegal move onto empty square deselects; illegal capture keeps selection
            if target == self._config.EMPTY_CELL:
                self._selected = None
            return

        self._board.set(*start, self._config.EMPTY_CELL)
        duration = self._config.move_duration(start, cell)
        self._resolver.add_move(Move(piece, start, cell, clock, clock + duration))
        self._selected = None

    def _is_legal_move(self, piece, start, end):
        from rules.piece_type import PieceType
        strategy = self._registry.get(PieceType.from_token(piece[1]))
        dr, dc = end[0] - start[0], end[1] - start[1]
        context = MoveContext(
            board=self._board,
            color=piece[0],
            start=start,
            end=end,
            target_occupied=not self._board.is_empty(*end),
        )
        return strategy.is_legal(dr, dc, context)
