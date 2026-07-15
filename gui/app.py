from __future__ import annotations

import time

import cv2

from game.engine import GameEngine
from gui.asset_loader import Assets
from gui.board_renderer import BoardRenderer as GuiBoardRenderer

_WINDOW   = "KungFu Chess"
_TARGET_FPS = 30
_FRAME_MS   = 1000 // _TARGET_FPS

_LEFT  = cv2.EVENT_LBUTTONDOWN
_RIGHT = cv2.EVENT_RBUTTONDOWN


def _fit_window(window_name: str, frame_w: int, frame_h: int) -> float:
    """Resize the window so the board fits entirely on screen.

    Returns the scale factor applied (1.0 means no scaling needed).
    OpenCV does not expose a reliable cross-platform screen-size API, so
    we create a tiny named window, query its rect, then use that to infer
    the usable desktop area.  A safe fallback of 900 px tall is used if
    the query returns zero.
    """
    # Query usable screen height via a temporary full-screen window trick.
    # cv2.getWindowImageRect returns (x, y, w, h) of the *image area*.
    probe = "__probe__"
    cv2.namedWindow(probe, cv2.WINDOW_NORMAL)
    cv2.setWindowProperty(probe, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    rect = cv2.getWindowImageRect(probe)
    cv2.destroyWindow(probe)

    screen_w = rect[2] if rect[2] > 0 else 1920
    screen_h = rect[3] if rect[3] > 0 else 1080

    # Leave a small margin for the OS title bar / taskbar
    usable_w = int(screen_w * 0.95)
    usable_h = int(screen_h * 0.90)

    scale = min(usable_w / frame_w, usable_h / frame_h, 1.0)
    win_w  = int(frame_w * scale)
    win_h  = int(frame_h * scale)

    cv2.resizeWindow(window_name, win_w, win_h)
    return scale


class App:
    """OpenCV game loop.  Owns the window, clock, and mouse callbacks."""

    def __init__(self, engine: GameEngine, assets: Assets, config):
        self._engine  = engine
        self._config  = config
        self._cell    = assets.cell_px
        self._renderer = GuiBoardRenderer(
            assets,
            board_height=engine.board_height,
            board_width=engine.board_width,
        )
        self._last_tick = time.monotonic()
        self._scale     = 1.0   # set after window creation

    def run(self) -> None:
        frame_w = self._engine.board_width  * self._cell
        frame_h = self._engine.board_height * self._cell

        cv2.namedWindow(_WINDOW, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(_WINDOW, frame_w, frame_h)   # initial size
        self._scale = _fit_window(_WINDOW, frame_w, frame_h)

        cv2.setMouseCallback(_WINDOW, self._on_mouse)

        while True:
            now   = time.monotonic()
            dt_ms = int((now - self._last_tick) * 1000)
            self._last_tick = now

            self._engine.wait(dt_ms)

            frame = self._renderer.render(
                board_snapshot=self._engine.snapshot(),
                empty=self._config.EMPTY_CELL,
                clock_ms=self._engine.clock,
                selected=self._engine.selected,
                active_moves=self._engine.active_moves,
                active_jumps=self._engine.active_jumps,
            )

            if self._engine.game_over:
                _overlay_game_over(frame)

            cv2.imshow(_WINDOW, frame)

            key = cv2.waitKey(_FRAME_MS) & 0xFF
            if key == 27 or cv2.getWindowProperty(_WINDOW, cv2.WND_PROP_VISIBLE) < 1:
                break

        cv2.destroyAllWindows()

    def _on_mouse(self, event, x, y, flags, param) -> None:
        # Mouse coordinates from OpenCV are always in *frame* pixels even
        # when the window is scaled, so no inverse-scale needed.
        if event == _LEFT:
            self._engine.handle_click(x, y)
        elif event == _RIGHT:
            self._engine.handle_jump(x, y)


def _overlay_game_over(frame: np.ndarray) -> None:
    import numpy as np
    h, w = frame.shape[:2]
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (w, h), (0, 0, 0, 200), -1)
    cv2.addWeighted(overlay, 0.55, frame, 0.45, 0, frame)
    cv2.putText(frame, "GAME OVER",
                (w // 2 - 140, h // 2),
                cv2.FONT_HERSHEY_SIMPLEX, 2.0,
                (0, 255, 200, 255), 3, cv2.LINE_AA)
