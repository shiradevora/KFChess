"""KungFu Chess – graphical entry point.

Run from any directory:
    python path/to/main_gui.py
"""
import os
import sys

# Insert the project root (the directory containing this file) at the front
# of sys.path so all package imports work regardless of working directory.
_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from config import settings
from board.text_board import TextBoardRepresentation
from rules.rule_registry import build_default_registry
from rules.game_conditions import KingCaptureWinCondition, LastRankPromotion
from game.engine import GameEngine
from gui.asset_loader import Assets
from gui.app import App

_DEFAULT_BOARD = [
    "bR bN bB bQ bK bB bN bR".split(),
    "bP bP bP bP bP bP bP bP".split(),
    ". . . . . . . .".split(),
    ". . . . . . . .".split(),
    ". . . . . . . .".split(),
    ". . . . . . . .".split(),
    "wP wP wP wP wP wP wP wP".split(),
    "wR wN wB wQ wK wB wN wR".split(),
]


def main():
    board = TextBoardRepresentation(_DEFAULT_BOARD, empty_token=settings.EMPTY_CELL)
    engine = GameEngine(
        board=board,
        rule_registry=build_default_registry(settings),
        win_condition=KingCaptureWinCondition(),
        promotion_rule=LastRankPromotion(),
        config=settings,
    )
    App(engine, Assets(cell_px=settings.CELL_SIZE), config=settings).run()


if __name__ == "__main__":
    main()
