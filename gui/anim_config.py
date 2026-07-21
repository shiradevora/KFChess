"""gui/anim_config.py

Responsible solely for parsing and holding the data from a state's
config.json.  All dictionary access uses .get() with explicit defaults
so that future schema changes never raise KeyError elsewhere.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass

from gui.sprite_state import SpriteState


@dataclass(frozen=True)
class AnimConfig:
    """Immutable value object produced by AnimConfigParser."""
    fps: float
    is_loop: bool
    next_state: SpriteState


class AnimConfigParser:
    """Reads a state folder's config.json and returns an AnimConfig.

    Injected into AnimState so AnimState never touches the filesystem
    or knows about JSON structure.

    The JSON string for next_state (e.g. "idle") is converted to a
    SpriteState enum member here — this is the single external boundary
    where raw strings become typed values.
    """

    _DEFAULTS = {
        "fps": 8.0,
        "is_loop": True,
        "next_state": SpriteState.IDLE,
    }

    def parse(self, folder: str) -> AnimConfig:
        path = os.path.join(folder, "config.json")
        with open(path) as f:
            raw = json.load(f)

        graphics = raw.get("graphics", {})
        physics  = raw.get("physics",  {})

        raw_next = physics.get("next_state_when_finished")
        next_state = (
            SpriteState(raw_next)
            if raw_next is not None
            else self._DEFAULTS["next_state"]
        )

        return AnimConfig(
            fps        = float(graphics.get("frames_per_sec", self._DEFAULTS["fps"])),
            is_loop    = bool( graphics.get("is_loop",        self._DEFAULTS["is_loop"])),
            next_state = next_state,
        )
