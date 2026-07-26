"""protocol/mapper.py

The single translation point between the domain (game/state_snapshot.py,
game/models.py) and the wire (protocol/messages.py). GameSession must go
through snapshot_to_event() rather than constructing GameStateEvent by hand.
"""
from __future__ import annotations

from game.state_snapshot import GameStateSnapshot
from protocol.messages import GameStateEvent, JumpDTO, MoveDTO


def snapshot_to_event(snapshot: GameStateSnapshot) -> GameStateEvent:
    active_moves = tuple(
        MoveDTO(
            move_id=move.move_id,
            piece=move.piece,
            start=move.start,
            end=move.end,
            dispatch_ms=move.dispatch_ms,
            arrival=move.arrival,
        )
        for move in snapshot.active_moves
    )
    active_jumps = tuple(
        JumpDTO(
            jump_id=jump.jump_id,
            piece=jump.piece,
            cell=jump.cell,
            end_time=jump.end_time,
        )
        for jump in snapshot.active_jumps
    )
    return GameStateEvent(
        clock_ms=snapshot.clock_ms,
        board_tokens=snapshot.board_tokens,
        board_height=snapshot.board_height,
        board_width=snapshot.board_width,
        active_moves=active_moves,
        active_jumps=active_jumps,
        selected_cell=snapshot.selected_cell,
        game_over=snapshot.game_over,
        empty_token=snapshot.empty_token,
    )
