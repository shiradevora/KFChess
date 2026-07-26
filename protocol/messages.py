"""protocol/messages.py

Wire messages for KungFu Chess.

These frozen dataclasses are the ONLY objects allowed to cross a network
boundary (client <-> server). Never pass a GameStateSnapshot, Move, Jump,
or any other engine/domain object directly to a transport layer — always
translate through protocol/mapper.py first. Keeping the wire format as a
small, explicit set of DTOs means the domain model is free to change shape
without breaking wire compatibility, and the wire format is free to add
versioning/discrimination concerns the domain has no business knowing about.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ClickCommand:
    x: int
    y: int
    type: str = "click"


@dataclass(frozen=True)
class JumpCommand:
    x: int
    y: int
    type: str = "jump"


@dataclass(frozen=True)
class MoveDTO:
    move_id:     str
    piece:       str
    start:       tuple
    end:         tuple
    dispatch_ms: float
    arrival:     float


@dataclass(frozen=True)
class JumpDTO:
    jump_id:  str
    piece:    str
    cell:     tuple
    end_time: float


@dataclass(frozen=True)
class GameStateEvent:
    clock_ms:      float
    board_tokens:  tuple
    board_height:  int
    board_width:   int
    active_moves:  tuple
    active_jumps:  tuple
    selected_cell: tuple | None
    game_over:     bool
    empty_token:   str
    type:          str = "game_state"


@dataclass(frozen=True)
class ErrorMessage:
    message: str
    type:    str = "error"
