from __future__ import annotations

import time

import cv2

from game.engine import GameEngine
from gui.asset_loader import Assets
from gui.board_renderer import BoardRenderer as GuiBoardRenderer

_WINDOW = "KungFu Chess"
_TARGET_FPS = 30
_FRAME_MS = 1000 // _TARGET_FPS

_LEFT = cv2.EVENT_LBUTTONDOWN
_RIGHT = cv2.EVENT_RBUTTONDOWN


class App:
    """OpenCV game loop.  Owns the window, clock, and mouse callbacks."""

    def __init__(self, engine: GameEngine, assets: Assets, config):
        self._engine = engine
        self._config = config
        self._renderer = GuiBoardRenderer(
            assets,
            board_height=engine.board_height,
            board_width=engine.board_width,
        )
        self._last_tick = time.monotonic()

    def run(self) -> None:
        cv2.namedWindow(_WINDOW)
        cv2.setMouseCallback(_WINDOW, self._on_mouse)

        while True:
            now = time.monotonic()
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
                self._overlay_game_over(frame)

            cv2.imshow(_WINDOW, frame)

            key = cv2.waitKey(_FRAME_MS) & 0xFF
            if key == 27 or cv2.getWindowProperty(_WINDOW, cv2.WND_PROP_VISIBLE) < 1:
                break

        cv2.destroyAllWindows()

    def _on_mouse(self, event, x, y, flags, param) -> None:
        if event == _LEFT:
            self._engine.handle_click(x, y)
        elif event == _RIGHT:
            self._engine.handle_jump(x, y)

    @staticmethod
    def _overlay_game_over(frame) -> None:
        h, w = frame.shape[:2]
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, 0), (w, h), (0, 0, 0, 180), -1)
        cv2.addWeighted(overlay, 0.5, frame, 0.5, 0, frame)
        cv2.putText(frame, "GAME OVER", (w // 2 - 120, h // 2),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.8, (0, 255, 200, 255), 3, cv2.LINE_AA)
