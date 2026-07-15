from __future__ import annotations

import os

import cv2
import numpy as np

from gui.sprite import PieceSprite

# All paths are resolved relative to this file so they work from any
# working directory.
_GUI_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_GUI_DIR)
_ANIMATE_ROOT = os.path.join(_PROJECT_ROOT, "animate")
_PIECES_ROOT = os.path.join(_ANIMATE_ROOT, "pieces2")
_BOARD_PATH = os.path.join(_ANIMATE_ROOT, "boardImg", "board.png")


class Assets:
    """Holds the board image and a factory for per-piece sprites."""

    def __init__(self, cell_px: int):
        self.cell_px = cell_px
        self.board_img = self._load_board()

    def _load_board(self) -> np.ndarray:
        img = cv2.imread(_BOARD_PATH, cv2.IMREAD_UNCHANGED)
        if img is None:
            raise FileNotFoundError(f"Board image not found: {_BOARD_PATH}")
        if img.shape[2] == 3:
            img = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
        return img

    def sprite(self, token: str) -> PieceSprite:
        """Return a new PieceSprite for `token` (one per board cell)."""
        return PieceSprite(token, _PIECES_ROOT, self.cell_px)
