"""rules/piece_type.py

PieceType enum — the strongly-typed identity of a chess piece kind.

Replaces the brittle raw-string registry keys ("K", "Q", …) with an
enum so that:
  * Typos are caught at import time, not at runtime.
  * IDEs and type-checkers can verify every usage.
  * Adding a new piece kind is a single-line change here, not a
    scattered search-and-replace across multiple files.

The `token` property returns the single-character board token so that
existing board-parsing and rendering code that works with strings
continues to work without modification.
"""
from __future__ import annotations

from enum import Enum


class PieceType(Enum):
    KING   = "K"
    QUEEN  = "Q"
    ROOK   = "R"
    BISHOP = "B"
    KNIGHT = "N"
    PAWN   = "P"

    @property
    def token(self) -> str:
        """Single-character board token (e.g. PieceType.KING.token == 'K')."""
        return self.value

    @staticmethod
    def from_token(token: str) -> "PieceType":
        """Look up a PieceType by its single-character token.

        Raises ValueError for unknown tokens, which is caught by the
        registry and re-raised as UnknownPieceKindError.
        """
        for member in PieceType:
            if member.value == token:
                return member
        raise ValueError(f"Unknown piece token: {token!r}")
