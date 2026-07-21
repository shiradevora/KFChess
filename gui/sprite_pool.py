"""gui/sprite_pool.py  –  Controller layer: sprite lifecycle management.

Responsibilities
----------------
- Track which PieceSprite belongs to each board cell (stationary pieces).
- Track which PieceSprite is in transit for each active move, along with
  the dispatch timestamp needed for linear interpolation.
- Drive animation state transitions (idle → move → long_rest, jump →
  short_rest → idle) by calling PieceSprite.set_state at the right moment.
- Produce a list of DrawCommand objects each tick that the View
  (BoardRenderer) can render without knowing anything about game state.

What this module does NOT do
-----------------------------
- No rendering / cv2 calls.
- No game-rule validation.
- No file I/O.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from gui.asset_loader import Assets
from gui.sprite import PieceSprite
from gui.sprite_state import SpriteState


@dataclass
class DrawCommand:
    """Everything BoardRenderer needs to blit one piece frame."""
    frame: np.ndarray   # pre-resized BGRA numpy array
    x: int              # pixel x on the canvas
    y: int              # pixel y on the canvas


class SpritePool:
    """Manages all PieceSprite instances and produces DrawCommands.

    Parameters are fully injected — no direct asset paths or config here.
    """

    def __init__(self, assets: Assets, cell_px: int):
        self._assets  = assets
        self._cell    = cell_px
        # (row, col) → PieceSprite  for stationary pieces
        self._cell_sprites: dict[tuple[int, int], PieceSprite] = {}
        # id(move) → (PieceSprite, move, dispatch_ms)
        self._move_sprites: dict[int, tuple[PieceSprite, object, float]] = {}

    def update(self,
               snapshot: list[list[str]],
               empty: str,
               clock_ms: float,
               active_moves,
               active_jumps) -> list[DrawCommand]:
        """Sync sprite pools with current game state; return draw commands."""
        self._sync_move_sprites(active_moves, clock_ms)
        self._sync_cell_sprites(snapshot, empty, clock_ms, active_jumps)
        return self._build_commands(snapshot, empty, clock_ms)

    # ------------------------------------------------------------------
    # Sprite pool synchronisation
    # ------------------------------------------------------------------

    def _sync_move_sprites(self, active_moves, clock_ms: float) -> None:
        active_ids = {id(m) for m in active_moves}

        for move in active_moves:
            mid = id(move)
            if mid not in self._move_sprites:
                sprite = self._assets.build_sprite(move.piece)
                sprite.set_state(SpriteState.MOVE, clock_ms)
                self._move_sprites[mid] = (sprite, move, clock_ms)

        for mid in list(self._move_sprites):
            if mid not in active_ids:
                sprite, move, _ = self._move_sprites.pop(mid)
                sprite.set_state(SpriteState.LONG_REST, clock_ms, force=True)
                self._cell_sprites[move.end] = sprite

    def _sync_cell_sprites(self, snapshot, empty, clock_ms, active_jumps) -> None:
        jumping_cells = {j.cell for j in active_jumps}

        live: set[tuple[int, int]] = set()
        for r, row in enumerate(snapshot):
            for c, token in enumerate(row):
                if token == empty:
                    continue
                live.add((r, c))
                existing = self._cell_sprites.get((r, c))
                if existing is None or existing.token != token:
                    # New piece or promotion — build a fresh sprite
                    self._cell_sprites[(r, c)] = self._assets.build_sprite(token)
                if (r, c) in jumping_cells:
                    self._cell_sprites[(r, c)].set_state(SpriteState.JUMP, clock_ms, force=True)

        for key in list(self._cell_sprites):
            if key not in live:
                del self._cell_sprites[key]

    # ------------------------------------------------------------------
    # DrawCommand assembly
    # ------------------------------------------------------------------

    def _build_commands(self, snapshot, empty, clock_ms: float) -> list[DrawCommand]:
        commands: list[DrawCommand] = []

        # Stationary pieces
        for (r, c), sprite in self._cell_sprites.items():
            if snapshot[r][c] == empty:
                continue
            commands.append(DrawCommand(
                frame=sprite.frame(clock_ms),
                x=c * self._cell,
                y=r * self._cell,
            ))

        # In-transit pieces — linearly interpolated position
        for sprite, move, dispatch_ms in self._move_sprites.values():
            total_ms = max(move.arrival - dispatch_ms, 1.0)
            progress = max(0.0, min(1.0, (clock_ms - dispatch_ms) / total_ms))
            sr, sc = move.start
            er, ec = move.end
            commands.append(DrawCommand(
                frame=sprite.frame(clock_ms),
                x=int(sc * self._cell + (ec - sc) * self._cell * progress),
                y=int(sr * self._cell + (er - sr) * self._cell * progress),
            ))

        return commands
