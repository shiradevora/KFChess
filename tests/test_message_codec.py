import json

import pytest

from protocol.codec import DecodeError, decode, encode
from protocol.messages import (
    ClickCommand,
    ErrorMessage,
    GameStateEvent,
    JumpCommand,
    JumpDTO,
    MoveDTO,
)


def test_round_trip_click_command():
    original = ClickCommand(x=150, y=250)
    decoded = decode(encode(original))
    assert decoded == original


def test_round_trip_jump_command():
    original = JumpCommand(x=50, y=350)
    decoded = decode(encode(original))
    assert decoded == original


def test_round_trip_error_message():
    original = ErrorMessage(message="No commands can be accepted: the game is already over.")
    decoded = decode(encode(original))
    assert decoded == original


def test_decode_raises_on_invalid_json():
    with pytest.raises(DecodeError):
        decode("{not valid json")


def test_decode_raises_on_missing_type():
    with pytest.raises(DecodeError):
        decode(json.dumps({"x": 1, "y": 2}))


def test_decode_raises_on_unknown_type():
    with pytest.raises(DecodeError):
        decode(json.dumps({"type": "teleport", "x": 1, "y": 2}))


def test_encode_game_state_event_round_trips_nested_dtos_through_dict_form():
    move = MoveDTO(
        move_id="m1", piece="wR", start=(0, 0), end=(0, 2),
        dispatch_ms=0.0, arrival=1000.0,
    )
    jump = JumpDTO(jump_id="m2", piece="bP", cell=(1, 1), end_time=500.0)
    event = GameStateEvent(
        clock_ms=10.0,
        board_tokens=(("wR", ".", "."), (".", ".", ".")),
        board_height=2,
        board_width=3,
        active_moves=(move,),
        active_jumps=(jump,),
        selected_cell=None,
        game_over=False,
        empty_token=".",
    )

    payload = json.loads(encode(event))

    assert payload["type"] == "game_state"
    assert payload["active_moves"] == [
        {"move_id": "m1", "piece": "wR", "start": [0, 0], "end": [0, 2],
         "dispatch_ms": 0.0, "arrival": 1000.0}
    ]
    assert payload["active_jumps"] == [
        {"jump_id": "m2", "piece": "bP", "cell": [1, 1], "end_time": 500.0}
    ]
    assert payload["board_tokens"] == [["wR", ".", "."], [".", ".", "."]]
