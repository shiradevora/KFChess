"""game/move_resolver.py

MoveResolver — settles in-flight moves and jumps each tick.

Responsibilities
----------------
* Advance the internal clock by delta_ms each tick.
* Settle any Move whose arrival time has passed.
* Expire any Jump whose end_time has passed.
* Detect trajectory intersections between pairs of active moves
  (the hook for future air-collision support).
* Raise domain exceptions (CollisionError) rather than silently
  resolving ambiguous states.

What this class does NOT do
---------------------------
* No pixel / screen-space knowledge.
* No input handling.
* No rendering.
"""
from __future__ import annotations

from game.exceptions import CollisionError
from game.models import Move, Jump


class MoveResolver:

    def __init__(self, board, win_condition, promotion_rule, config):
        self._board           = board
        self._win_condition   = win_condition
        self._promotion_rule  = promotion_rule
        self._config          = config
        self._clock_ms: float = 0.0
        self._active_moves:  list[Move] = []
        self._active_jumps:  list[Jump] = []
        self._game_over:     bool       = False
        self._cooldowns:     dict[tuple, float] = {}  # cell -> cooldown_end_ms

    # ------------------------------------------------------------------
    # Public read-only properties
    # ------------------------------------------------------------------

    @property
    def game_over(self) -> bool:
        return self._game_over

    @property
    def clock_ms(self) -> float:
        return self._clock_ms

    @property
    def active_moves(self) -> tuple[Move, ...]:
        return tuple(self._active_moves)

    @property
    def active_jumps(self) -> tuple[Jump, ...]:
        return tuple(self._active_jumps)

    # ------------------------------------------------------------------
    # Mutation — called only by GameEngine
    # ------------------------------------------------------------------

    def add_move(self, move: Move) -> None:
        self._active_moves.append(move)

    def add_jump(self, jump: Jump) -> None:
        self._active_jumps.append(jump)

    def is_busy(self, cell: tuple) -> bool:
        return (
            any(m.start == cell for m in self._active_moves)
            or any(j.cell == cell for j in self._active_jumps)
            or self._cooldowns.get(cell, 0.0) > self._clock_ms
        )

    def update(self, delta_ms: float) -> None:
        """Advance the clock by *delta_ms* and settle any arrived moves."""
        self._clock_ms += delta_ms
        self._resolve_air_collisions()
        self._settle_arrived_moves()
        self._expire_jumps()
        self._clear_expired_cooldowns()

    # ------------------------------------------------------------------
    # Internal resolution helpers
    # ------------------------------------------------------------------

    def _settle_arrived_moves(self) -> None:
        remaining: list[Move] = []
        for move in self._active_moves:
            if self._clock_ms < move.arrival:
                remaining.append(move)
            else:
                self._settle_move(move)
                self._cooldowns[move.end] = move.arrival + self._config.LONG_COOLDOWN_MS
        self._active_moves = remaining

    def _expire_jumps(self) -> None:
        remaining: list[Jump] = []
        for j in self._active_jumps:
            if self._clock_ms < j.end_time:
                remaining.append(j)
            else:
                self._cooldowns[j.cell] = j.end_time + self._config.SHORT_COOLDOWN_MS
        self._active_jumps = remaining

    def _clear_expired_cooldowns(self) -> None:
        self._cooldowns = {
            cell: end for cell, end in self._cooldowns.items()
            if end > self._clock_ms
        }

    def _settle_move(self, move: Move) -> None:
        r, c = move.end

        # Intercepted by an enemy jump on the destination cell
        if any(j.cell == (r, c) and j.piece[0] != move.piece[0]
               for j in self._active_jumps):
            return

        target = self._board.get(r, c)

        # Friendly piece already occupies the destination — discard
        if target != self._config.EMPTY_CELL and target[0] == move.piece[0]:
            return

        captured = None if target == self._config.EMPTY_CELL else target
        if self._win_condition.is_game_over(captured):
            self._game_over = True

        piece = self._promotion_rule.promote(move.piece, r, self._board.height)
        self._board.set(r, c, piece)

    # ------------------------------------------------------------------
    # Air-collision detection
    # ------------------------------------------------------------------

    def _resolve_air_collisions(self) -> None:
        """Discard later-dispatched moves that collide with an opposite-color
        move arriving at the same cell this tick.  First-dispatched wins.
        Stores the last resolved CollisionError on self.last_collision for
        observability (animation / sound hooks can read it).
        """
        arrived = [m for m in self._active_moves if m.arrival <= self._clock_ms]
        losers: set[int] = set()
        last_collision: CollisionError | None = None
        for i in range(len(arrived)):
            for j in range(i + 1, len(arrived)):
                a, b = arrived[i], arrived[j]
                if a.piece[0] == b.piece[0] or a.end != b.end:
                    continue
                winner = a if a.dispatch_ms <= b.dispatch_ms else b
                loser  = b if a.dispatch_ms <= b.dispatch_ms else a
                losers.add(id(loser))
                last_collision = CollisionError(
                    move_a=winner, move_b=loser,
                    collision_cell=loser.end, collision_ms=self._clock_ms,
                )
        if losers:
            self._active_moves = [m for m in self._active_moves if id(m) not in losers]
            self.last_collision = last_collision  # observable by callers
