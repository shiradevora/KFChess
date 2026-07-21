"""rules/rule_registry.py

PieceRuleRegistry — maps PieceType → MovementStrategy.

Internal dictionary keys are strictly PieceType enum members.
register() enforces this at authoring time — passing a raw string
raises TypeError immediately.
get() is the single dynamic boundary where a raw board token string
(e.g. piece[1] from "wK") is converted to PieceType at runtime.
"""
from __future__ import annotations

from rules.piece_type import PieceType
from rules.movement_strategy import MovementStrategy


class UnknownPieceKindError(Exception):
    """Raised when a piece-kind token has no registered strategy."""


class PieceRuleRegistry:

    def __init__(self):
        self._strategies: dict[PieceType, MovementStrategy] = {}

    def register(self, piece_type: PieceType, strategy: MovementStrategy) -> None:
        """Register *strategy* for *piece_type*.

        Only PieceType enum members are accepted.  Passing a raw string
        raises TypeError so the mistake is caught at the registration
        site, not silently at lookup time.
        """
        if not isinstance(piece_type, PieceType):
            raise TypeError(
                f"register() requires a PieceType enum member, got {piece_type!r}. "
                f"Use PieceType.from_token('{piece_type}') to convert a string."
            )
        self._strategies[piece_type] = strategy

    def get(self, piece_type: PieceType | str) -> MovementStrategy:
        """Return the strategy for *piece_type*.

        This is the single dynamic boundary where a raw single-character
        string token (e.g. piece[1] from a board cell) is converted to a
        PieceType.  All internal authoring code should pass PieceType
        directly.
        """
        if isinstance(piece_type, str):
            try:
                piece_type = PieceType.from_token(piece_type)
            except ValueError:
                raise UnknownPieceKindError(piece_type) from None
        try:
            return self._strategies[piece_type]
        except KeyError:
            raise UnknownPieceKindError(piece_type) from None

    def registered_kinds(self) -> tuple[str, ...]:
        """Return registered piece tokens as strings for parser compatibility."""
        return tuple(pt.token for pt in self._strategies)


def build_default_registry(config) -> PieceRuleRegistry:
    """Assemble the standard chess piece set using PieceType enum members."""
    from rules.piece_rules import (
        KingMovement, QueenMovement, RookMovement,
        BishopMovement, KnightMovement, PawnMovement,
    )

    registry = PieceRuleRegistry()
    registry.register(PieceType.KING,   KingMovement())
    registry.register(PieceType.QUEEN,  QueenMovement())
    registry.register(PieceType.ROOK,   RookMovement())
    registry.register(PieceType.BISHOP, BishopMovement())
    registry.register(PieceType.KNIGHT, KnightMovement())
    registry.register(PieceType.PAWN,
                      PawnMovement(config.PAWN_DIRECTION, config.PAWN_START_ROW))
    return registry
