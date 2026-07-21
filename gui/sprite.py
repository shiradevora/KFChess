"""gui/sprite.py  –  View layer: animation state machine.

Responsibilities
----------------
- AnimState  : holds pre-resized frames for one animation state and
               advances the frame index using real elapsed time (delta-time).
- PieceSprite: owns the state machine for one piece token; returns the
               correct pre-resized frame on every render tick.

What this module does NOT do
-----------------------------
- No file I/O  (all assets are loaded and injected by asset_loader.py).
- No cv2.resize at runtime  (frames are pre-scaled at load time).
- No game logic  (state transitions are driven by the Controller).
"""
from __future__ import annotations

import numpy as np

from gui.anim_config import AnimConfig
from gui.sprite_state import SpriteState


class AnimState:
    """One animation state backed by pre-resized frames.

    Parameters are fully injected — no filesystem access here.
    """

    def __init__(self, config: AnimConfig, frames: list[np.ndarray]):
        self._config = config
        self._frames = frames

    @property
    def is_loop(self) -> bool:
        return self._config.is_loop

    @property
    def next_state(self) -> SpriteState:
        return self._config.next_state

    @property
    def duration_ms(self) -> float:
        return len(self._frames) / self._config.fps * 1000

    def frame_at(self, elapsed_ms: float) -> np.ndarray:
        """Return the frame for the given elapsed time within this state."""
        total = self.duration_ms
        t = elapsed_ms % total if self._config.is_loop else min(elapsed_ms, total - 1e-6)
        idx = int(t / total * len(self._frames))
        idx = max(0, min(idx, len(self._frames) - 1))
        return self._frames[idx]


class PieceSprite:
    """Animation state machine for one piece token (e.g. 'wK').

    All AnimState objects are injected via the constructor — this class
    contains zero asset-loading or resizing logic.

    Public interface used by the Controller (SpritePool)
    -----------------------------------------------------
    set_state(state, clock_ms, force=False)
    frame(clock_ms) -> np.ndarray
    token  (read-only str)
    """

    def __init__(self, token: str, states: dict[SpriteState, AnimState]):
        self.token = token
        self._states = states
        self._current: SpriteState = SpriteState.IDLE
        self._state_start_ms = 0.0

    def set_state(self, state: SpriteState, clock_ms: float, force: bool = False) -> None:
        """Transition to *state*.  Ignored if already there unless force=True."""
        if state != self._current or force:
            self._current = state
            self._state_start_ms = clock_ms

    def frame(self, clock_ms: float) -> np.ndarray:
        anim    = self._states[self._current]
        elapsed = clock_ms - self._state_start_ms

        if not anim.is_loop and elapsed >= anim.duration_ms:
            # Non-looping state finished — advance to next state
            self.set_state(anim.next_state, self._state_start_ms + anim.duration_ms)
            return self.frame(clock_ms)

        return anim.frame_at(elapsed)
