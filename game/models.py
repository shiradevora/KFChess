"""game/models.py

Domain value objects for in-flight game actions.

Both are frozen dataclasses — immutable once created, hashable, and
safe to include in the GameStateSnapshot without defensive copying.

Move.dispatch_ms
    The clock time (ms) at which the move was issued.  Together with
    Move.arrival this defines the full trajectory window, which the
    MoveResolver uses to detect whether two moves' paths intersect
    (air-collision support).

    ETA  = arrival - dispatch_ms   (total travel time in ms)
    progress(t) = (t - dispatch_ms) / ETA   clamped to [0, 1]
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Move:
    piece:       str    # board token, e.g. 'wR'
    start:       tuple  # (row, col)
    end:         tuple  # (row, col)
    dispatch_ms: float  # clock time when the move was issued
    arrival:     float  # clock time when the piece lands


@dataclass(frozen=True)
class Jump:
    piece:    str    # board token of the jumping piece
    cell:     tuple  # (row, col) cell being defended
    end_time: float  # clock time when the jump expires
