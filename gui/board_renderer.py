from __future__ import annotations

import numpy as np
import cv2

from gui.asset_loader import Assets
from gui.img import Img
from gui.sprite import PieceSprite

# BGRA highlight colours
_SEL_COLOR = (0, 255, 100, 120)    # green tint – selected piece
_MOVE_COLOR = (255, 200, 0, 80)    # amber tint – piece in transit
_JUMP_COLOR = (0, 100, 255, 80)    # blue tint  – piece jumping


class BoardRenderer:
    """Composites the full game frame each tick.

    Owns a sprite per live piece token so animations are independent.
    """

    def __init__(self, assets: Assets, board_height: int, board_width: int):
        self._assets = assets
        self._rows = board_height
        self._cols = board_width
        self._cell = assets.cell_px
        self._sprites: dict[tuple[int, int], PieceSprite] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def render(self,
               board_snapshot: list[list[str]],
               empty: str,
               clock_ms: float,
               selected: tuple[int, int] | None,
               active_moves,
               active_jumps) -> np.ndarray:

        self._sync_sprites(board_snapshot, empty, clock_ms, active_moves, active_jumps)

        canvas = Img()
        canvas.img = self._scaled_board()

        self._draw_highlights(canvas, selected, active_moves, active_jumps)
        self._draw_pieces(canvas, board_snapshot, empty, clock_ms, active_moves)

        return canvas.img

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _scaled_board(self) -> np.ndarray:
        target = (self._cols * self._cell, self._rows * self._cell)
        return cv2.resize(self._assets.board_img, target, interpolation=cv2.INTER_AREA).copy()

    def _sync_sprites(self, snapshot, empty, clock_ms, active_moves, active_jumps):
        """Create sprites for new pieces; update animation states."""
        moving_starts = {m.start for m in active_moves}
        jumping_cells = {j.cell for j in active_jumps}

        for r, row in enumerate(snapshot):
            for c, token in enumerate(row):
                if token == empty:
                    self._sprites.pop((r, c), None)
                    continue
                if (r, c) not in self._sprites:
                    self._sprites[(r, c)] = self._assets.sprite(token)
                sprite = self._sprites[(r, c)]
                if (r, c) in jumping_cells:
                    sprite.set_state("jump", clock_ms)
                elif (r, c) in moving_starts:
                    sprite.set_state("move", clock_ms)

        # Remove sprites for cells that no longer exist in snapshot
        live = {(r, c) for r, row in enumerate(snapshot) for c, t in enumerate(row) if t != empty}
        for key in list(self._sprites):
            if key not in live:
                del self._sprites[key]

    def _draw_highlights(self, canvas: Img, selected, active_moves, active_jumps):
        if selected:
            self._fill_cell(canvas, *selected, _SEL_COLOR)
        for move in active_moves:
            self._fill_cell(canvas, *move.end, _MOVE_COLOR)
        for jump in active_jumps:
            self._fill_cell(canvas, *jump.cell, _JUMP_COLOR)

    def _draw_pieces(self, canvas: Img, snapshot, empty, clock_ms, active_moves):
        moving_starts = {m.start for m in active_moves}
        for r, row in enumerate(snapshot):
            for c, token in enumerate(row):
                if token == empty or (r, c) in moving_starts:
                    continue
                sprite = self._sprites.get((r, c))
                if sprite is None:
                    continue
                frame_img = Img()
                frame_img.img = sprite.frame(clock_ms)
                x = c * self._cell
                y = r * self._cell
                frame_img.draw_on(canvas, x, y)

    def _fill_cell(self, canvas: Img, row: int, col: int, color: tuple):
        x, y = col * self._cell, row * self._cell
        overlay = canvas.img.copy()
        cv2.rectangle(overlay, (x, y), (x + self._cell, y + self._cell), color, -1)
        cv2.addWeighted(overlay, color[3] / 255.0, canvas.img,
                        1 - color[3] / 255.0, 0, canvas.img)
