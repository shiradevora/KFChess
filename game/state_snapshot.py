"""game/state_snapshot.py

GameStateSnapshot — a lightweight, immutable Data Transfer Object (DTO)
that represents the complete observable state of the game at one tick.

Design decisions
----------------
* frozen=True  — external layers cannot mutate engine state through this
  object; any attempt raises FrozenInstanceError immediately.
* board_tokens is a tuple-of-tuples so it is hashable and cannot be
  accidentally mutated by the GUI or a network serialiser.
* active_moves / active_jumps are tuples of the Move / Jump value
  objects from game.models — also frozen dataclasses, so the whole
  snapshot is deeply immutable.
* The engine exposes *only* get_state() → GameStateSnapshot.  No other
  internal getter is needed by external layers.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GameStateSnapshot:
    """Read-only view of the game at a specific clock tick.

    Attributes
    ----------
    clock_ms      : current game clock in milliseconds
    board_tokens  : tuple[tuple[str, ...], ...] — row-major token grid
    board_height  : number of rows
    board_width   : number of columns
    active_moves  : tuple of Move objects currently in flight
    active_jumps  : tuple of Jump objects currently active
    selected_cell : (row, col) of the currently selected piece, or None
    game_over     : True once a win condition has been triggered
    empty_token   : the string used to represent an empty cell
    """
    clock_ms:      float
    board_tokens:  tuple
    board_height:  int
    board_width:   int
    active_moves:  tuple
    active_jumps:  tuple
    selected_cell: tuple | None
    game_over:     bool
    empty_token:   str
