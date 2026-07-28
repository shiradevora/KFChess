"""protocol/codec.py

JSON encode/decode for the wire messages defined in protocol/messages.py.
"""
from __future__ import annotations

import dataclasses
import json

from protocol.messages import (
    ClickCommand,
    ErrorMessage,
    GameStateEvent,
    JumpCommand,
    JumpDTO,
    LoginCommand,
    MessageType,
    MoveDTO,
    RegisterCommand,
)


class DecodeError(Exception):
    """Raised when a JSON string cannot be decoded into a wire message."""


def encode(message: object) -> str:
    return json.dumps(dataclasses.asdict(message))


def _decode_move_dto(data: dict) -> MoveDTO:
    return MoveDTO(
        move_id=data["move_id"],
        piece=data["piece"],
        start=tuple(data["start"]),
        end=tuple(data["end"]),
        dispatch_ms=data["dispatch_ms"],
        arrival=data["arrival"],
    )


def _decode_jump_dto(data: dict) -> JumpDTO:
    return JumpDTO(
        jump_id=data["jump_id"],
        piece=data["piece"],
        cell=tuple(data["cell"]),
        end_time=data["end_time"],
    )


def _decode_game_state_event(data: dict) -> GameStateEvent:
    selected_cell = data["selected_cell"]
    return GameStateEvent(
        clock_ms=data["clock_ms"],
        board_tokens=tuple(tuple(row) for row in data["board_tokens"]),
        board_height=data["board_height"],
        board_width=data["board_width"],
        active_moves=tuple(_decode_move_dto(m) for m in data["active_moves"]),
        active_jumps=tuple(_decode_jump_dto(j) for j in data["active_jumps"]),
        selected_cell=tuple(selected_cell) if selected_cell is not None else None,
        game_over=data["game_over"],
        empty_token=data["empty_token"],
    )


_DECODERS = {
    MessageType.CLICK: lambda data: ClickCommand(x=data["x"], y=data["y"]),
    MessageType.JUMP: lambda data: JumpCommand(x=data["x"], y=data["y"]),
    MessageType.ERROR: lambda data: ErrorMessage(message=data["message"]),
    MessageType.GAME_STATE: _decode_game_state_event,
    MessageType.LOGIN: lambda data: LoginCommand(username=data["username"], password=data["password"]),
    MessageType.REGISTER: lambda data: RegisterCommand(username=data["username"], password=data["password"]),
}


def decode(json_str: str) -> object:
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as exc:
        raise DecodeError(f"invalid JSON: {exc}") from exc

    if not isinstance(data, dict) or "type" not in data:
        raise DecodeError("missing 'type' field")

    try:
        msg_type = MessageType(data["type"])
    except ValueError:
        raise DecodeError(f"unrecognized 'type': {data['type']!r}")

    decoder = _DECODERS[msg_type]

    try:
        return decoder(data)
    except (KeyError, TypeError, ValueError) as exc:
        raise DecodeError(f"malformed payload for type {msg_type!r}: {exc}") from exc
