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
from enum import Enum


class MessageType(str, Enum):
    """str subclass Enum: instances serialize directly as plain strings via
    json.dumps — no custom encoder needed, and equality/hashing still works
    against plain string values for backward JSON compatibility.
    """
    CLICK = "click"
    JUMP = "jump"
    GAME_STATE = "game_state"
    ERROR = "error"
    LOGIN = "login"
    REGISTER = "register"


@dataclass(frozen=True)
class ClickCommand:
    x: int
    y: int
    type: MessageType = MessageType.CLICK


@dataclass(frozen=True)
class JumpCommand:
    x: int
    y: int
    type: MessageType = MessageType.JUMP


@dataclass(frozen=True)
class LoginCommand:
    username: str
    password: str
    type: MessageType = MessageType.LOGIN


@dataclass(frozen=True)
class RegisterCommand:
    username: str
    password: str
    type: MessageType = MessageType.REGISTER


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
    type:          MessageType = MessageType.GAME_STATE


@dataclass(frozen=True)
class ErrorMessage:
    message: str
    type:    MessageType = MessageType.ERROR
