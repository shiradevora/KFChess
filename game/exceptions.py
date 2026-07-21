"""game/exceptions.py

Domain exceptions for KungFu Chess.

All exceptions carry enough structured data to be serialised and
reflected across a client/server boundary without the receiver needing
to parse a free-form message string.
"""
from __future__ import annotations


class KFChessError(Exception):
    """Base class for all domain errors."""


class InvalidMoveError(KFChessError):
    """Raised when a requested move violates the movement rules.

    Attributes
    ----------
    piece   : token of the piece that was asked to move (e.g. 'wR')
    start   : (row, col) origin cell
    end     : (row, col) destination cell
    reason  : human-readable explanation (safe to surface to the client)
    """

    def __init__(self, piece: str, start: tuple, end: tuple, reason: str = ""):
        self.piece  = piece
        self.start  = start
        self.end    = end
        self.reason = reason
        super().__init__(f"Invalid move {piece} {start}->{end}: {reason}")


class CollisionError(KFChessError):
    """Raised (or available to be raised) when two trajectories intersect.

    Designed for the future air-collision mechanic: the resolver detects
    that two in-flight moves will occupy the same cell at the same time
    and raises this instead of silently resolving one over the other.

    Attributes
    ----------
    move_a, move_b : the two Move objects whose trajectories intersect
    collision_cell : (row, col) where the collision occurs
    collision_ms   : estimated clock time of the collision
    """

    def __init__(self, move_a, move_b, collision_cell: tuple, collision_ms: float):
        self.move_a         = move_a
        self.move_b         = move_b
        self.collision_cell = collision_cell
        self.collision_ms   = collision_ms
        super().__init__(
            f"Air collision at {collision_cell} (~{collision_ms:.0f} ms) "
            f"between {move_a.piece} and {move_b.piece}"
        )


class GameOverError(KFChessError):
    """Raised when a command is dispatched after the game has ended."""

    def __init__(self):
        super().__init__("No commands can be accepted: the game is already over.")


class BoardParseError(KFChessError):
    """Raised when the board definition cannot be parsed."""
