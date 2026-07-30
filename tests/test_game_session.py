from board.text_board import TextBoardRepresentation
from config import settings
from rules.game_conditions import KingCaptureWinCondition, LastRankPromotion
from rules.rule_registry import build_default_registry
from game.engine import GameEngine
from application.game_session import GameSession
from infrastructure.bus.in_memory_bus import InMemoryEventBus
from protocol.messages import ErrorMessage, GameStateEvent


def make_session(rows, session_id="s1"):
    board = TextBoardRepresentation(rows)
    engine = GameEngine(
        board=board,
        rule_registry=build_default_registry(settings),
        win_condition=KingCaptureWinCondition(),
        promotion_rule=LastRankPromotion(),
        config=settings,
    )
    bus = InMemoryEventBus()
    received = []
    bus.subscribe(f"session:{session_id}", received.append)
    session = GameSession(session_id, engine, bus)
    return session, board, received


def cell_to_pixel(row, col):
    return col * settings.CELL_SIZE, row * settings.CELL_SIZE


def test_handle_click_on_empty_cell_publishes_event_with_no_selection():
    session, board, received = make_session([["wK", "."], [".", "."]])

    session.handle_click(*cell_to_pixel(1, 1), acting_color="white")

    assert len(received) == 1
    event = received[-1]
    assert isinstance(event, GameStateEvent)
    assert event.selected_cell is None


def test_handle_click_select_then_move_publishes_one_active_move_dto():
    session, board, received = make_session(
        [["wR", ".", "."], [".", ".", "."], [".", ".", "."]]
    )

    session.handle_click(*cell_to_pixel(0, 0), acting_color="white")
    session.handle_click(*cell_to_pixel(0, 2), acting_color="white")

    event = received[-1]
    assert isinstance(event, GameStateEvent)
    assert len(event.active_moves) == 1
    assert event.active_moves[0].move_id


def test_tick_after_arrival_settles_move_and_clears_active_moves():
    session, board, received = make_session(
        [["wR", ".", "."], [".", ".", "."], [".", ".", "."]]
    )

    session.handle_click(*cell_to_pixel(0, 0), acting_color="white")
    session.handle_click(*cell_to_pixel(0, 2), acting_color="white")
    session.tick(2 * settings.MOVE_DURATION)

    event = received[-1]
    assert event.active_moves == ()
    assert event.board_tokens[0][2] == "wR"


def test_handle_click_after_game_over_publishes_error_message_instead_of_raising():
    rows = [["wR", ".", "bK"], [".", ".", "."], [".", ".", "."]]
    session, board, received = make_session(rows)

    session.handle_click(*cell_to_pixel(0, 0), acting_color="white")
    session.handle_click(*cell_to_pixel(0, 2), acting_color="white")
    session.tick(2 * settings.MOVE_DURATION)
    assert received[-1].game_over is True

    received.clear()
    session.handle_click(*cell_to_pixel(0, 0), acting_color="white")

    assert any(isinstance(event, ErrorMessage) for event in received)


def test_handle_jump_after_game_over_publishes_error_message_instead_of_raising():
    rows = [["wR", ".", "bK"], [".", ".", "."], [".", ".", "."]]
    session, board, received = make_session(rows)

    session.handle_click(*cell_to_pixel(0, 0), acting_color="white")
    session.handle_click(*cell_to_pixel(0, 2), acting_color="white")
    session.tick(2 * settings.MOVE_DURATION)

    received.clear()
    session.handle_jump(*cell_to_pixel(0, 2), acting_color="white")

    assert any(isinstance(event, ErrorMessage) for event in received)


# ----------------------------------------------------------------------
# Color enforcement: a connection may only ever act on its own color's
# pieces — checked against the piece being selected/acted on, never the
# destination cell (captures onto an enemy-occupied cell stay entirely the
# engine/rules' job, unchanged).
# ----------------------------------------------------------------------

def test_acting_as_white_clicking_a_white_piece_succeeds_normally():
    session, board, received = make_session(
        [["wR", ".", "bR"], [".", ".", "."], [".", ".", "."]]
    )

    session.handle_click(*cell_to_pixel(0, 0), acting_color="white")

    event = received[-1]
    assert isinstance(event, GameStateEvent)
    assert event.selected_cell == (0, 0)


def test_acting_as_white_clicking_a_black_piece_is_rejected_with_error_message():
    session, board, received = make_session(
        [["wR", ".", "bR"], [".", ".", "."], [".", ".", "."]]
    )

    session.handle_click(*cell_to_pixel(0, 2), acting_color="white")

    assert len(received) == 1
    assert isinstance(received[0], ErrorMessage)


def test_rejected_click_leaves_engine_state_completely_unchanged():
    session, board, received = make_session(
        [["wR", ".", "bR"], [".", ".", "."], [".", ".", "."]]
    )

    session.handle_click(*cell_to_pixel(0, 2), acting_color="white")  # rejected: black piece
    received.clear()

    # If the rejected click had actually selected the black rook, this next
    # click (on an unrelated empty cell) would be read as "move the
    # selected piece here" and mutate the board. Since nothing was ever
    # selected, it's just another no-op empty-cell click instead.
    session.handle_click(*cell_to_pixel(1, 1), acting_color="white")

    assert received[-1].selected_cell is None
    assert board.get(0, 0) == "wR"
    assert board.get(0, 2) == "bR"


def test_acting_as_white_attempting_to_move_selected_black_piece_is_rejected():
    session, board, received = make_session(
        [["bR", ".", "."], [".", ".", "."], [".", ".", "."]]
    )
    # Selected as black — a black-acting connection selecting its own piece.
    session.handle_click(*cell_to_pixel(0, 0), acting_color="black")
    received.clear()

    # Now a white-acting connection tries to move that already-selected
    # (black) piece — must be rejected on the source piece's color.
    session.handle_click(*cell_to_pixel(0, 2), acting_color="white")

    assert len(received) == 1
    assert isinstance(received[0], ErrorMessage)
    assert board.get(0, 0) == "bR"  # never moved


def test_acting_as_white_jump_on_a_black_piece_is_rejected_with_error_message():
    session, board, received = make_session(
        [["wR", ".", "bR"], [".", ".", "."], [".", ".", "."]]
    )

    session.handle_jump(*cell_to_pixel(0, 2), acting_color="white")

    assert len(received) == 1
    assert isinstance(received[0], ErrorMessage)
