"""gui/asset_loader.py  –  Infrastructure layer: asset loading & caching.

Responsibilities
----------------
- Locate asset files relative to this file (works from any working directory).
- Load and resize ALL images exactly once at startup.
- Expose a build_sprite(token) factory that constructs a fully-injected
  PieceSprite with pre-resized frames — no I/O or resizing happens later.

What this module does NOT do
-----------------------------
- No game logic.
- No rendering.
- No runtime cv2.resize calls after __init__ completes.
"""
from __future__ import annotations

import os

import cv2
import numpy as np

from gui.anim_config import AnimConfig, AnimConfigParser
from gui.sprite import AnimState, PieceSprite
from gui.sprite_state import SpriteState

# ---------------------------------------------------------------------------
# Path constants — all relative to this file so they survive any cwd
# ---------------------------------------------------------------------------
_GUI_DIR      = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_GUI_DIR)
_ANIMATE_ROOT = os.path.join(_PROJECT_ROOT, "animate")
_PIECES_ROOT  = os.path.join(_ANIMATE_ROOT, "pieces2")
_BOARD_PATH   = os.path.join(_ANIMATE_ROOT, "boardImg", "board.png")

_COLOR_SUFFIX = {"w": "W", "b": "B"}
_STATES       = list(SpriteState)


class Assets:
    """Loads and caches every asset at construction time.

    Parameters
    ----------
    cell_px : int
        The pixel size of one board cell.  All piece frames are resized
        to (cell_px × cell_px) here, once, so the render loop never
        calls cv2.resize.
    config_parser : AnimConfigParser | None
        Injected parser for animation JSON.  Defaults to AnimConfigParser()
        so callers that don't need a custom parser stay simple.
    """

    def __init__(self, cell_px: int,
                 config_parser: AnimConfigParser | None = None):
        self.cell_px       = cell_px
        self._parser       = config_parser or AnimConfigParser()
        self.board_img     = self._load_board(cell_px)
        # Pre-build AnimState dicts for every piece token, keyed by token
        self._state_cache: dict[str, dict[str, AnimState]] = {}
        self._preload_all_pieces(cell_px)

    # ------------------------------------------------------------------
    # Public factory
    # ------------------------------------------------------------------

    def build_sprite(self, token: str) -> PieceSprite:
        """Return a new PieceSprite with pre-loaded, pre-resized frames."""
        return PieceSprite(token, self._state_cache[token])

    # ------------------------------------------------------------------
    # Private loading helpers
    # ------------------------------------------------------------------

    def _load_board(self, cell_px: int) -> np.ndarray:
        img = cv2.imread(_BOARD_PATH, cv2.IMREAD_UNCHANGED)
        if img is None:
            raise FileNotFoundError(f"Board image not found: {_BOARD_PATH}")
        if img.shape[2] == 3:
            img = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
        # Pre-scale board to exact canvas size (8×8 assumed; renderer will use as-is)
        board_rows = 8
        board_cols = 8
        img = cv2.resize(img, (board_cols * cell_px, board_rows * cell_px),
                         interpolation=cv2.INTER_AREA)
        return img

    def _preload_all_pieces(self, cell_px: int) -> None:
        tokens = [
            f"{color}{kind}"
            for color in ("w", "b")
            for kind in ("K", "Q", "R", "B", "N", "P")
        ]
        for token in tokens:
            self._state_cache[token] = self._load_states(token, cell_px)

    def _load_states(self, token: str, cell_px: int) -> dict[SpriteState, AnimState]:
        folder = os.path.join(
            _PIECES_ROOT,
            f"{token[1]}{_COLOR_SUFFIX[token[0]]}",
            "states",
        )
        return {
            state: self._load_one_state(os.path.join(folder, state.value), cell_px)
            for state in _STATES
        }

    def _load_one_state(self, folder: str, cell_px: int) -> AnimState:
        config: AnimConfig = self._parser.parse(folder)
        frames = self._load_frames(os.path.join(folder, "sprites"), cell_px)
        return AnimState(config, frames)

    @staticmethod
    def _load_frames(sprites_dir: str, cell_px: int) -> list[np.ndarray]:
        paths = sorted(
            (os.path.join(sprites_dir, f) for f in os.listdir(sprites_dir)),
            key=lambda p: int(os.path.splitext(os.path.basename(p))[0]),
        )
        frames = []
        for p in paths:
            img = cv2.imread(p, cv2.IMREAD_UNCHANGED)
            if img is None:
                raise FileNotFoundError(f"Sprite frame not found: {p}")
            # Resize once here — never again during the game loop
            img = cv2.resize(img, (cell_px, cell_px), interpolation=cv2.INTER_AREA)
            frames.append(img)
        return frames
