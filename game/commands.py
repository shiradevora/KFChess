"""game/commands.py

Explicit domain command objects.

The engine accepts these; it never receives raw pixel coordinates,
hardware events, or network payloads.  The CommandDispatcher (or any
future network deserialiser) is responsible for constructing them.

All commands are frozen dataclasses — immutable value objects that can
be logged, queued, replayed, or serialised without side effects.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SelectCommand:
    """Request to select (or deselect) a piece at a logical board cell.

    Attributes
    ----------
    cell : (row, col) of the cell the player tapped.
           None means "deselect whatever is currently selected".
    """
    cell: tuple | None


@dataclass(frozen=True)
class MoveCommand:
    """Request to move the currently selected piece to *end*.

    Attributes
    ----------
    start : (row, col) origin — the cell that was selected
    end   : (row, col) destination the player chose
    """
    start: tuple
    end: tuple


@dataclass(frozen=True)
class JumpCommand:
    """Request to make the piece at *cell* perform a defensive jump.

    Attributes
    ----------
    cell : (row, col) of the piece to jump
    """
    cell: tuple
