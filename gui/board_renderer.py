"""gui/board_renderer.py  –  View layer: passive canvas compositor.

Responsibilities
----------------
- Accept a RenderFrame data object from the Controller.
- Draw the board background, cell highlights, and piece frames onto a
  numpy canvas in the correct order.
- Return the finished numpy array to the caller.

What this module does NOT do
-----------------------------
- No game logic or rule validation.
- No sprite lifecycle management (that lives in SpritePool).
- No file I/O or image resizing.
- No direct access to GameEngine or Assets.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

from gui.img import Img
from gui.sprite_pool import DrawCommand

# BGRA highlight colours
_SEL_COLOR  = (0,   255, 100, 120)   # green  – selected piece
_MOVE_COLOR = (255, 200, 0,   80)    # amber  – move destination
_JUMP_COLOR = (0,   100, 255, 80)    # blue   – jumping piece


@dataclass
class RenderFrame:
    """Pure data object assembled by the Controller each tick.

    BoardRenderer reads this and nothing else — it never touches the
    engine, the board, or any sprite pool directly.
    """
    board_img:    np.ndarray                      # pre-scaled board background
    draw_commands: list[DrawCommand]              # pieces to blit
    cell_px:      int                             # pixels per cell
    selected:     tuple[int, int] | None = None
    move_ends:    list[tuple[int, int]]  = field(default_factory=list)
    jump_cells:   list[tuple[int, int]]  = field(default_factory=list)
    game_over:    bool                   = False


class BoardRenderer:
    """Stateless compositor.  Every public method is a pure function of
    its inputs — no instance state is mutated between frames.
    """

    def render(self, rf: RenderFrame) -> np.ndarray:
        canvas = Img()
        canvas.img = rf.board_img.copy()

        self._draw_highlights(canvas, rf)
        self._draw_pieces(canvas, rf.draw_commands)

        if rf.game_over:
            self._draw_game_over(canvas.img)

        return canvas.img

    # ------------------------------------------------------------------
    # Private drawing helpers
    # ------------------------------------------------------------------

    def _draw_highlights(self, canvas: Img, rf: RenderFrame) -> None:
        if rf.selected:
            self._fill_cell(canvas, rf.selected[0], rf.selected[1],
                            rf.cell_px, _SEL_COLOR)
        for (r, c) in rf.move_ends:
            self._fill_cell(canvas, r, c, rf.cell_px, _MOVE_COLOR)
        for (r, c) in rf.jump_cells:
            self._fill_cell(canvas, r, c, rf.cell_px, _JUMP_COLOR)

    @staticmethod
    def _draw_pieces(canvas: Img, commands: list[DrawCommand]) -> None:
        for cmd in commands:
            piece_img = Img()
            piece_img.img = cmd.frame
            piece_img.draw_on(canvas, cmd.x, cmd.y)

    @staticmethod
    def _fill_cell(canvas: Img, row: int, col: int,
                   cell_px: int, color: tuple) -> None:
        x, y = col * cell_px, row * cell_px
        overlay = canvas.img.copy()
        cv2.rectangle(overlay, (x, y), (x + cell_px, y + cell_px), color, -1)
        cv2.addWeighted(overlay, color[3] / 255.0,
                        canvas.img, 1 - color[3] / 255.0, 0, canvas.img)

    @staticmethod
    def _draw_game_over(frame: np.ndarray) -> None:
        h, w = frame.shape[:2]
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, 0), (w, h), (0, 0, 0, 200), -1)
        cv2.addWeighted(overlay, 0.55, frame, 0.45, 0, frame)
        cv2.putText(frame, "GAME OVER",
                    (w // 2 - 140, h // 2),
                    cv2.FONT_HERSHEY_SIMPLEX, 2.0,
                    (0, 255, 200, 255), 3, cv2.LINE_AA)
