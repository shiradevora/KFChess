from game.models import Move, Jump


class MoveResolver:
    def __init__(self, board, win_condition, promotion_rule, config):
        self._board = board
        self._win_condition = win_condition
        self._promotion_rule = promotion_rule
        self._config = config
        self._active_moves = []
        self._active_jumps = []
        self._game_over = False

    @property
    def game_over(self):
        return self._game_over

    @property
    def active_moves(self):
        return tuple(self._active_moves)

    @property
    def active_jumps(self):
        return tuple(self._active_jumps)

    def add_move(self, move: Move):
        self._active_moves.append(move)

    def add_jump(self, jump: Jump):
        self._active_jumps.append(jump)

    def is_busy(self, cell):
        return (
            any(m.start == cell for m in self._active_moves)
            or any(j.cell == cell for j in self._active_jumps)
        )

    def resolve(self, clock):
        remaining = []
        for move in self._active_moves:
            if clock < move.arrival:
                remaining.append(move)
            else:
                self._settle_move(move)
        self._active_moves = remaining
        self._active_jumps = [j for j in self._active_jumps if clock < j.end_time]

    def _settle_move(self, move):
        r, c = move.end
        if any(j.cell == (r, c) and j.piece[0] != move.piece[0] for j in self._active_jumps):
            return

        target = self._board.get(r, c)
        if target != self._config.EMPTY_CELL and target[0] == move.piece[0]:
            return

        captured = None if target == self._config.EMPTY_CELL else target
        if self._win_condition.is_game_over(captured):
            self._game_over = True

        piece = self._promotion_rule.promote(move.piece, r, self._board.height)
        self._board.set(r, c, piece)
