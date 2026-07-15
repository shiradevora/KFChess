from __future__ import annotations

import json
import os

import cv2

# Maps board token color prefix → folder suffix under animate/pieces2/
# e.g. "wK" → "KW",  "bP" → "PB"
_COLOR_SUFFIX = {"w": "W", "b": "B"}

STATES = ("idle", "move", "jump", "short_rest", "long_rest")


class AnimState:
    """One animation state: frames + timing config loaded from disk."""

    def __init__(self, folder: str):
        with open(os.path.join(folder, "config.json")) as f:
            cfg = json.load(f)
        self.fps: float = cfg["graphics"]["frames_per_sec"]
        self.is_loop: bool = cfg["graphics"]["is_loop"]
        self.next_state: str = cfg["physics"]["next_state_when_finished"]

        sprites_dir = os.path.join(folder, "sprites")
        frame_paths = sorted(
            (os.path.join(sprites_dir, f) for f in os.listdir(sprites_dir)),
            key=lambda p: int(os.path.splitext(os.path.basename(p))[0])
        )
        self.frames = [cv2.imread(p, cv2.IMREAD_UNCHANGED) for p in frame_paths]

    @property
    def duration_ms(self) -> float:
        return len(self.frames) / self.fps * 1000


class PieceSprite:
    """Animated sprite for one piece token (e.g. 'wK').

    Call `set_state` when the piece starts moving/jumping/resting.
    Call `frame(clock_ms)` each render tick to get the current numpy frame.
    """

    def __init__(self, token: str, pieces_root: str, cell_px: int):
        folder = os.path.join(
            pieces_root,
            f"{token[1]}{_COLOR_SUFFIX[token[0]]}",
            "states"
        )
        self.token = token
        self._states: dict[str, AnimState] = {
            s: AnimState(os.path.join(folder, s)) for s in STATES
        }
        self._cell_px = cell_px
        self._current = "idle"
        self._state_start_ms = 0.0

    def set_state(self, state: str, clock_ms: float, force: bool = False) -> None:
        """Transition to `state` at `clock_ms`.

        Ignored if already in that state unless `force=True`, which is
        used when a piece needs to restart the same animation (e.g. a
        second long_rest after a second move).
        """
        if state != self._current or force:
            self._current = state
            self._state_start_ms = clock_ms

    def frame(self, clock_ms: float):
        anim = self._states[self._current]
        elapsed = clock_ms - self._state_start_ms
        total_ms = anim.duration_ms

        if not anim.is_loop and elapsed >= total_ms:
            self.set_state(anim.next_state, self._state_start_ms + total_ms)
            return self.frame(clock_ms)

        idx = int((elapsed % total_ms) / total_ms * len(anim.frames))
        idx = min(idx, len(anim.frames) - 1)
        raw = anim.frames[idx]
        return cv2.resize(raw, (self._cell_px, self._cell_px), interpolation=cv2.INTER_AREA)
