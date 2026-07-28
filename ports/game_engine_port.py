"""ports/game_engine_port.py

Shared structural contract between game.engine.GameEngine (local play) and
client.remote_engine.RemoteGameEngine (networked play). gui/app.py's App is
constructed with one or the other and treats them interchangeably — it only
ever touches the members declared here. Expressing that as a
typing.Protocol lets both engines satisfy the contract structurally (no
inheritance required, so neither class's construction or behavior changes),
while still letting a test assert conformance instead of relying on
convention alone.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class GameEnginePort(Protocol):
    """The subset of GameEngine/RemoteGameEngine that gui/app.py's App depends on."""

    @property
    def clock(self) -> float: ...

    @property
    def selected(self) -> tuple | None: ...

    @property
    def active_moves(self) -> tuple: ...

    @property
    def active_jumps(self) -> tuple: ...

    @property
    def game_over(self) -> bool: ...

    @property
    def board_width(self) -> int: ...

    @property
    def board_height(self) -> int: ...

    def snapshot(self) -> list: ...

    def handle_click(self, x: int, y: int) -> None: ...

    def handle_jump(self, x: int, y: int) -> None: ...


@runtime_checkable
class SelfTicking(Protocol):
    """Capability for an engine that owns and advances its own clock.

    Only local (non-networked) engines implement this — a networked
    engine's clock is owned by the server, so it must NOT claim this
    capability.
    """

    def wait(self, dt_ms: float) -> None: ...
