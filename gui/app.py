"""gui/app.py  –  Controller layer: game loop and coordination.

Responsibilities
----------------
- Own the OpenCV window and the real-time clock.
- Translate raw mouse events into engine calls (handle_click / handle_jump).
- Drive the SpritePool update each tick.
- Assemble a RenderFrame data object from engine state + sprite draw commands.
- Pass the RenderFrame to BoardRenderer and display the result.

What this module does NOT do
-----------------------------
- No rendering logic (all drawing is in BoardRenderer).
- No game-rule validation (all logic is in GameEngine).
- No asset loading (all assets are pre-loaded in Assets).
"""
from __future__ import annotations

import time

import cv2

from game.engine import GameEngine
from gui.asset_loader import Assets
from gui.board_renderer import BoardRenderer, RenderFrame
from gui.sprite_pool import SpritePool

_WINDOW     = "KungFu Chess"
_TARGET_FPS = 30
_FRAME_MS   = 1000 // _TARGET_FPS

_LEFT  = cv2.EVENT_LBUTTONDOWN
_RIGHT = cv2.EVENT_RBUTTONDOWN


def _detect_screen_size() -> tuple[int, int]:
    """Return (width, height) of the usable desktop area.

    Uses a temporary fullscreen probe window; falls back to 1920×1080
    if the query returns zero (e.g. headless environments).
    """
    probe = "__screen_probe__"
    cv2.namedWindow(probe, cv2.WINDOW_NORMAL)
    cv2.setWindowProperty(probe, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    rect = cv2.getWindowImageRect(probe)
    cv2.destroyWindow(probe)
    w = rect[2] if rect[2] > 0 else 1920
    h = rect[3] if rect[3] > 0 else 1080
    return w, h


class App:
    """Controller: coordinates engine, sprite pool, renderer, and window.

    All collaborators are injected via __init__ — nothing is instantiated
    internally, making the class straightforward to test with fakes.
    """

    def __init__(self, engine: GameEngine, assets: Assets, config):
        self._engine   = engine
        self._config   = config
        self._assets   = assets
        self._pool     = SpritePool(assets, assets.cell_px)
        self._renderer = BoardRenderer()
        self._last_tick = time.monotonic()

    def run(self) -> None:
        frame_w = self._engine.board_width  * self._assets.cell_px
        frame_h = self._engine.board_height * self._assets.cell_px

        cv2.namedWindow(_WINDOW, cv2.WINDOW_NORMAL)
        self._fit_window(frame_w, frame_h)
        cv2.setMouseCallback(_WINDOW, self._on_mouse)

        while True:
            now     = time.monotonic()
            dt_ms   = int((now - self._last_tick) * 1000)
            self._last_tick = now

            self._engine.wait(dt_ms)

            render_frame = self._build_render_frame()
            output = self._renderer.render(render_frame)
            cv2.imshow(_WINDOW, output)

            key = cv2.waitKey(_FRAME_MS) & 0xFF
            if key == 27 or cv2.getWindowProperty(_WINDOW, cv2.WND_PROP_VISIBLE) < 1:
                break

        cv2.destroyAllWindows()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_render_frame(self) -> RenderFrame:
        """Assemble all data the View needs — no rendering happens here."""
        engine    = self._engine
        clock_ms  = engine.clock
        snapshot  = engine.snapshot()
        active_moves = engine.active_moves
        active_jumps = engine.active_jumps

        draw_commands = self._pool.update(
            snapshot=snapshot,
            empty=self._config.EMPTY_CELL,
            clock_ms=clock_ms,
            active_moves=active_moves,
            active_jumps=active_jumps,
        )

        return RenderFrame(
            board_img     = self._assets.board_img,
            draw_commands = draw_commands,
            cell_px       = self._assets.cell_px,
            selected      = engine.selected,
            move_ends     = [m.end  for m in active_moves],
            jump_cells    = [j.cell for j in active_jumps],
            game_over     = engine.game_over,
        )

    def _on_mouse(self, event, x, y, flags, param) -> None:
        """Translate raw OpenCV mouse events into engine calls."""
        if event == _LEFT:
            self._engine.handle_click(x, y)
        elif event == _RIGHT:
            self._engine.handle_jump(x, y)

    def _fit_window(self, frame_w: int, frame_h: int) -> None:
        """Scale the window down to fit the usable screen area."""
        screen_w, screen_h = _detect_screen_size()
        usable_w = int(screen_w * 0.95)
        usable_h = int(screen_h * 0.90)
        scale    = min(usable_w / frame_w, usable_h / frame_h, 1.0)
        cv2.resizeWindow(_WINDOW, int(frame_w * scale), int(frame_h * scale))
