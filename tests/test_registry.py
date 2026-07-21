import pytest

from config import settings
from rules.piece_type import PieceType
from rules.rule_registry import PieceRuleRegistry, UnknownPieceKindError, build_default_registry
from rules.movement_strategy import MovementStrategy


class DummyStrategy(MovementStrategy):
    def is_legal(self, dr, dc, context):
        return True


def test_register_and_get_with_enum():
    """register() and get() both work with PieceType members."""
    registry = PieceRuleRegistry()
    strategy = DummyStrategy()
    registry.register(PieceType.KING, strategy)
    assert registry.get(PieceType.KING) is strategy


def test_get_accepts_string_at_dynamic_boundary():
    """get() converts a raw string token — simulates piece[1] from a board cell."""
    registry = PieceRuleRegistry()
    strategy = DummyStrategy()
    registry.register(PieceType.ROOK, strategy)
    assert registry.get("R") is strategy


def test_register_rejects_raw_string():
    """register() raises TypeError for raw strings — PieceType required."""
    registry = PieceRuleRegistry()
    with pytest.raises(TypeError):
        registry.register("K", DummyStrategy())


def test_unknown_enum_raises_on_get():
    registry = PieceRuleRegistry()
    with pytest.raises(UnknownPieceKindError):
        registry.get(PieceType.QUEEN)


def test_unknown_string_raises_on_get():
    registry = PieceRuleRegistry()
    with pytest.raises(UnknownPieceKindError):
        registry.get("Z")


def test_registered_kinds_returns_strings():
    """registered_kinds() returns string tokens for parser compatibility."""
    registry = PieceRuleRegistry()
    registry.register(PieceType.BISHOP, DummyStrategy())
    assert "B" in registry.registered_kinds()


def test_default_registry_has_all_standard_pieces():
    registry = build_default_registry(settings)
    for kind in ("K", "Q", "R", "B", "N", "P"):
        assert kind in registry.registered_kinds()
