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

    session.handle_click(*cell_to_pixel(1, 1))

    assert len(received) == 1
    event = received[-1]
    assert isinstance(event, GameStateEvent)
    assert event.selected_cell is None


def test_handle_click_select_then_move_publishes_one_active_move_dto():
    session, board, received = make_session(
        [["wR", ".", "."], [".", ".", "."], [".", ".", "."]]
    )

    session.handle_click(*cell_to_pixel(0, 0))
    session.handle_click(*cell_to_pixel(0, 2))

    event = received[-1]
    assert isinstance(event, GameStateEvent)
    assert len(event.active_moves) == 1
    assert event.active_moves[0].move_id


def test_tick_after_arrival_settles_move_and_clears_active_moves():
    session, board, received = make_session(
        [["wR", ".", "."], [".", ".", "."], [".", ".", "."]]
    )

    session.handle_click(*cell_to_pixel(0, 0))
    session.handle_click(*cell_to_pixel(0, 2))
    session.tick(2 * settings.MOVE_DURATION)

    event = received[-1]
    assert event.active_moves == ()
    assert event.board_tokens[0][2] == "wR"


def test_handle_click_after_game_over_publishes_error_message_instead_of_raising():
    rows = [["wR", ".", "bK"], [".", ".", "."], [".", ".", "."]]
    session, board, received = make_session(rows)

    session.handle_click(*cell_to_pixel(0, 0))
    session.handle_click(*cell_to_pixel(0, 2))
    session.tick(2 * settings.MOVE_DURATION)
    assert received[-1].game_over is True

    received.clear()
    session.handle_click(*cell_to_pixel(0, 0))

    assert any(isinstance(event, ErrorMessage) for event in received)


def test_handle_jump_after_game_over_publishes_error_message_instead_of_raising():
    rows = [["wR", ".", "bK"], [".", ".", "."], [".", ".", "."]]
    session, board, received = make_session(rows)

    session.handle_click(*cell_to_pixel(0, 0))
    session.handle_click(*cell_to_pixel(0, 2))
    session.tick(2 * settings.MOVE_DURATION)

    received.clear()
    session.handle_jump(*cell_to_pixel(0, 2))

    assert any(isinstance(event, ErrorMessage) for event in received)
