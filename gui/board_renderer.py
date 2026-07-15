from __future__ import annotations

import numpy as np
import cv2

from gui.asset_loader import Assets
from gui.img import Img
from gui.sprite import PieceSprite

# BGRA highlight colours
_SEL_COLOR  = (0,   255, 100, 120)   # green  – selected piece
_MOVE_COLOR = (255, 200, 0,   80)    # amber  – destination of in-transit piece
_JUMP_COLOR = (0,   100, 255, 80)    # blue   – jumping piece cell


class BoardRenderer:
    """Composites the full game frame each tick.

    Sprite pools
    ------------
    _cell_sprites  : (row, col) → PieceSprite
        Pieces sitting still on a cell (idle / short_rest / long_rest).

    _move_sprites  : id(move) → (PieceSprite, move, dispatch_ms)
        Pieces currently travelling between two cells.
        dispatch_ms is recorded when the move first appears so we can
        compute linear interpolation without storing extra data on Move.
    """

    def __init__(self, assets: Assets, board_height: int, board_width: int):
        self._assets = assets
        self._rows   = board_height
        self._cols   = board_width
        self._cell   = assets.cell_px

        self._cell_sprites: dict[tuple[int, int], PieceSprite] = {}
        # id(move) → (sprite, move, dispatch_ms)
        self._move_sprites: dict[int, tuple[PieceSprite, object, float]] = {}

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

        self._sync_move_sprites(active_moves, clock_ms)
        self._sync_cell_sprites(board_snapshot, empty, clock_ms, active_jumps)

        canvas = Img()
        canvas.img = self._scaled_board()

        self._draw_highlights(canvas, selected, active_moves, active_jumps)
        self._draw_cell_pieces(canvas, board_snapshot, empty, clock_ms)
        self._draw_moving_pieces(canvas, clock_ms)

        return canvas.img

    # ------------------------------------------------------------------
    # Sprite pool synchronisation
    # ------------------------------------------------------------------

    def _sync_move_sprites(self, active_moves, clock_ms: float):
        """Add sprites for new moves; retire sprites for resolved moves."""
        active_ids = {id(m) for m in active_moves}

        # New moves → create sprite, start "move" animation
        for move in active_moves:
            mid = id(move)
            if mid not in self._move_sprites:
                sprite = self._assets.sprite(move.piece)
                sprite.set_state("move", clock_ms)
                self._move_sprites[mid] = (sprite, move, clock_ms)

        # Resolved moves → hand sprite to _cell_sprites at destination,
        # transition to "long_rest" so the piece plays its landing animation.
        for mid in list(self._move_sprites):
            if mid not in active_ids:
                sprite, move, _ = self._move_sprites.pop(mid)
                sprite.set_state("long_rest", clock_ms, force=True)
                self._cell_sprites[move.end] = sprite

    def _sync_cell_sprites(self, snapshot, empty, clock_ms, active_jumps):
        """Keep _cell_sprites in sync with the board snapshot.

        Also replaces a sprite when the board token changes (e.g. pawn
        promotion: the cell now holds 'wQ' but the sprite was built for
        'wP').
        """
        jumping_cells = {j.cell for j in active_jumps}

        live: set[tuple[int, int]] = set()
        for r, row in enumerate(snapshot):
            for c, token in enumerate(row):
                if token == empty:
                    continue
                live.add((r, c))
                existing = self._cell_sprites.get((r, c))
                # Replace sprite if missing or if the piece token changed (promotion)
                if existing is None or existing.token != token:
                    self._cell_sprites[(r, c)] = self._assets.sprite(token)
                sprite = self._cell_sprites[(r, c)]
                if (r, c) in jumping_cells:
                    sprite.set_state("jump", clock_ms, force=True)

        for key in list(self._cell_sprites):
            if key not in live:
                del self._cell_sprites[key]

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def _scaled_board(self) -> np.ndarray:
        target = (self._cols * self._cell, self._rows * self._cell)
        return cv2.resize(self._assets.board_img, target,
                          interpolation=cv2.INTER_AREA).copy()

    def _draw_highlights(self, canvas: Img, selected, active_moves, active_jumps):
        if selected:
            self._fill_cell(canvas, *selected, _SEL_COLOR)
        for move in active_moves:
            self._fill_cell(canvas, *move.end, _MOVE_COLOR)
        for jump in active_jumps:
            self._fill_cell(canvas, *jump.cell, _JUMP_COLOR)

    def _draw_cell_pieces(self, canvas: Img, snapshot, empty, clock_ms: float):
        for (r, c), sprite in self._cell_sprites.items():
            if snapshot[r][c] == empty:
                continue
            self._blit(canvas, sprite, clock_ms, c * self._cell, r * self._cell)

    def _draw_moving_pieces(self, canvas: Img, clock_ms: float):
        """Draw each in-transit piece at its linearly interpolated position."""
        for sprite, move, dispatch_ms in self._move_sprites.values():
            total_ms = move.arrival - dispatch_ms
            elapsed  = clock_ms - dispatch_ms
            progress = max(0.0, min(1.0, elapsed / total_ms if total_ms > 0 else 1.0))

            sr, sc = move.start
            er, ec = move.end
            x = int(sc * self._cell + (ec - sc) * self._cell * progress)
            y = int(sr * self._cell + (er - sr) * self._cell * progress)

            self._blit(canvas, sprite, clock_ms, x, y)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _blit(canvas: Img, sprite: PieceSprite, clock_ms: float, x: int, y: int):
        frame_img = Img()
        frame_img.img = sprite.frame(clock_ms)
        frame_img.draw_on(canvas, x, y)

    def _fill_cell(self, canvas: Img, row: int, col: int, color: tuple):
        x, y = col * self._cell, row * self._cell
        overlay = canvas.img.copy()
        cv2.rectangle(overlay, (x, y),
                      (x + self._cell, y + self._cell), color, -1)
        cv2.addWeighted(overlay, color[3] / 255.0,
                        canvas.img, 1 - color[3] / 255.0, 0, canvas.img)
