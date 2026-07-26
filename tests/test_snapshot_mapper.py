from game.models import Jump, Move
from game.state_snapshot import GameStateSnapshot
from protocol.mapper import snapshot_to_event
from protocol.messages import JumpDTO, MoveDTO


def make_snapshot(active_moves=(), active_jumps=(), selected_cell=None, game_over=False):
    return GameStateSnapshot(
        clock_ms=0.0,
        board_tokens=(("wR", "."), (".", ".")),
        board_height=2,
        board_width=2,
        active_moves=active_moves,
        active_jumps=active_jumps,
        selected_cell=selected_cell,
        game_over=game_over,
        empty_token=".",
    )


def test_snapshot_with_no_activity_maps_to_empty_tuples():
    snapshot = make_snapshot()

    event = snapshot_to_event(snapshot)

    assert event.active_moves == ()
    assert event.active_jumps == ()
    assert event.board_tokens == snapshot.board_tokens
    assert event.clock_ms == snapshot.clock_ms
    assert event.selected_cell is None
    assert event.game_over is False


def test_snapshot_with_one_move_and_one_jump_maps_every_field():
    move = Move(
        piece="wR", move_id="m1", start=(0, 0), end=(0, 1),
        dispatch_ms=100.0, arrival=1100.0,
    )
    jump = Jump(piece="bP", jump_id="m2", cell=(1, 1), end_time=600.0)
    snapshot = make_snapshot(active_moves=(move,), active_jumps=(jump,))

    event = snapshot_to_event(snapshot)

    assert event.active_moves == (
        MoveDTO(
            move_id="m1", piece="wR", start=(0, 0), end=(0, 1),
            dispatch_ms=100.0, arrival=1100.0,
        ),
    )
    assert event.active_jumps == (
        JumpDTO(jump_id="m2", piece="bP", cell=(1, 1), end_time=600.0),
    )
