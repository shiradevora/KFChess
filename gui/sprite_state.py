"""gui/sprite_state.py — Enum of all valid piece animation states."""
from __future__ import annotations

from enum import Enum


class SpriteState(str, Enum):
    """All valid animation states for a piece sprite.

    Inherits from str so that values double as filesystem folder names
    (e.g. os.path.join(folder, state.value)) without extra conversion.
    """
    IDLE       = "idle"
    MOVE       = "move"
    JUMP       = "jump"
    SHORT_REST = "short_rest"
    LONG_REST  = "long_rest"
