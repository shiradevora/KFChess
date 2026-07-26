"""protocol/codec.py

JSON encode/decode for the wire messages defined in protocol/messages.py.
"""
from __future__ import annotations

import dataclasses
import json

from protocol.messages import ClickCommand, ErrorMessage, JumpCommand


class DecodeError(Exception):
    """Raised when a JSON string cannot be decoded into a wire message."""


def encode(message: object) -> str:
    return json.dumps(dataclasses.asdict(message))


_DECODERS = {
    "click": lambda data: ClickCommand(x=data["x"], y=data["y"]),
    "jump": lambda data: JumpCommand(x=data["x"], y=data["y"]),
    "error": lambda data: ErrorMessage(message=data["message"]),
}


def decode(json_str: str) -> object:
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as exc:
        raise DecodeError(f"invalid JSON: {exc}") from exc

    if not isinstance(data, dict) or "type" not in data:
        raise DecodeError("missing 'type' field")

    msg_type = data["type"]
    decoder = _DECODERS.get(msg_type)
    if decoder is None:
        raise DecodeError(f"unrecognized 'type': {msg_type!r}")

    try:
        return decoder(data)
    except KeyError as exc:
        raise DecodeError(f"missing field {exc} for type {msg_type!r}") from exc
