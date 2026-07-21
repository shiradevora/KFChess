import pytest
import sys
import io
from main import main

# ריכוז כל מקרי הבדיקה שקיבלנו מהלימודים
RAW_TESTS = """
Case = parse_empty_board_3x3
Input =Board:
. . .
. . .
. . .
Commands:
print board
Output =. . .
. . .
. . .

Case = parse_rectangular_board_3x4
Input =Board:
wK . . bK
. . . .
wR . . bR
Commands:
print board
Output =wK . . bK
. . . .
wR . . bR

Case = parse_piece_tokens_and_colors
Input =Board:
wK . bQ
. wN .
bP . wR
Commands:
print board
Output =wK . bQ
. wN .
bP . wR

Case = reject_unknown_token
Input =Board:
wK xZ
. .
Commands:
Output =ERROR UNKNOWN_TOKEN

Case = reject_row_width_mismatch
Input =Board:
wK . .
. bK
Commands:
Output =ERROR ROW_WIDTH_MISMATCH

Case = select_piece_by_center_click
Input = Board:
wK . .
. . .
. . .
Commands:
click 50 50
click 150 150
wait 1000
print board
Output = . . .
. wK .
. . .

Case = click_empty_cell_does_not_select
Input = Board:
wK . .
. . .
. . .
Commands:
click 150 150
click 250 250
wait 1000
print board
Output = wK . .
. . .
. . .

Case = click_outside_board_is_ignored
Input = Board:
wK . .
. . .
. . .
Commands:
click 350 50
click -10 50
print board
Output = wK . .
. . .
. . .

Case = clicking_another_piece_replaces_selection
Input = Board:
wR . wK
. . .
Commands:
click 50 50
click 250 50
click 250 150
wait 1000
print board
Output = wR . .
. . wK

Case = king_one_step_valid
Input = Board:
wK . .
. . .
. . .
Commands:
click 50 50
click 150 150
wait 1000
print board
Output = . . .
. wK .
. . .

Case = king_two_steps_invalid
Input = Board:
wK . .
. . .
. . .
Commands:
click 50 50
click 250 250
wait 1000
print board
Output = wK . .
. . .
. . .

Case = rook_straight_valid
Input = Board:
wR . .
Commands:
click 50 50
click 250 50
wait 2000
print board
Output = . . wR

Case = rook_diagonal_invalid
Input = Board:
wR . .
. . .
. . .
Commands:
click 50 50
click 150 150
wait 1000
print board
Output = wR . .
. . .
. . .

Case = bishop_diagonal_valid
Input = Board:
wB . .
. . .
. . .
Commands:
click 50 50
click 250 250
wait 2000
print board
Output = . . .
. . .
. . wB

Case = knight_L_valid
Input = Board:
wN . .
. . .
. . .
Commands:
click 50 50
click 150 250
wait 3000
print board
Output = . . .
. . .
. wN .

Case = queen_diagonal_valid
Input = Board:
wQ . .
. . .
. . .
Commands:
click 50 50
click 250 250
wait 2000
print board
Output = . . .
. . .
. . wQ

Case = rook_blocked_by_own_piece
Input = Board:
wR wP .
Commands:
click 50 50
click 250 50
wait 2000
print board
Output = wR wP .

Case = bishop_blocked_by_own_piece
Input = Board:
wB . .
. wP .
. . .
Commands:
click 50 50
click 250 250
wait 2000
print board
Output = wB . .
. wP .
. . .

Case = knight_jumps_over_blockers
Input = Board:
wN wP .
wP . .
. . .
Commands:
click 50 50
click 150 250
wait 3000
print board
Output = . wP .
wP . .
. wN .

Case = cannot_capture_own_piece
Input = Board:
wR . wP
Commands:
click 50 50
click 250 50
wait 2000
print board
Output = wR . wP

Case = rook_captures_enemy_at_destination
Input = Board:
wR . bR
Commands:
click 50 50
click 250 50
wait 2000
print board
Output = . . wR

Case = pawn_cannot_capture_forward
Input = Board:
. bR .
. wP .
. . .
Commands:
click 150 150
click 150 50
wait 1000
print board
Output = . bR .
. wP .
. . .

Case = one_cell_move_before_arrival_board_unchanged
Input = Board:
wR . .
Commands:
click 50 50
click 150 50
wait 500
print board
Output = wR . .

Case = two_cell_move_before_and_after_arrival
Input = Board:
wR . .
Commands:
click 50 50
click 250 50
wait 1000
print board
wait 1000
print board
Output = wR . .
. . wR

Case = moving_piece_ignores_redirect
Input = Board:
wR . .
Commands:
click 50 50
click 250 50
wait 1000
click 50 50
click 150 50
wait 1000
print board
Output = . . wR

Case = opposite_colors_do_not_move_concurrently_in_common_route
Input = Board:
wR . .
. . .
bR . .
Commands:
click 50 50
click 250 50
click 50 250
click 250 250
wait 2000
print board
Output = . . wR
. . .
bR . .

Case = no_cooldown_state_in_common_route
Input = Board:
wR . .
Commands:
click 50 50
click 150 50
wait 1000
print board
Output = . wR .

Case = can_move_again_after_arrival_without_cooldown
Input = Board:
wR . .
Commands:
click 50 50
click 150 50
wait 2000
click 150 50
click 250 50
wait 2000
print board
Output = . . wR

Case = piece_is_ready_after_arrival_without_cooldown
Input = Board:
wR . .
Commands:
click 50 50
click 150 50
wait 2000
click 150 50
click 250 50
wait 2000
print board
Output = . . wR

Case = enemy_collision_white_started_first
Input = Board:
wR . . bR
Commands:
click 50 50
click 350 50
click 350 50
click 50 50
wait 3000
print board
Output = . . . wR

Case = enemy_collision_black_started_first
Input = Board:
wR . . bR
Commands:
click 350 50
click 50 50
click 50 50
click 350 50
wait 3000
print board
Output = bR . . .

Case = cannot_start_move_through_friendly_piece
Input = Board:
. . .
wR wP .
. . .
Commands:
click 50 150
click 250 150
wait 2000
print board
Output = . . .
wR wP .
. . .

Case = dynamic_block_tactic_not_in_common_route
Input = Board:
. . . .
wQ . . bK
. . bP .
. . . .
Commands:
click 50 150
click 350 150
wait 200
click 250 250
click 250 150
wait 3000
print board
Output = . . . .
. . . wQ
. . bP .
. . . .

Case = knight_cannot_land_on_friendly_piece
Input = Board:
. wP .
. . .
wN . .
Commands:
click 50 250
click 150 50
wait 1000
print board
Output = . wP .
. . .
wN . .

Case = premove_does_not_execute_in_common_route
Input = Board:
wR . .
Commands:
click 50 50
click 150 50
click 50 50
click 250 50
wait 2000
print board
Output = . wR .

Case = king_capture_ends_game
Input = Board:
wR . bK
Commands:
click 50 50
click 250 50
wait 2000
print board
Output = . . wR

Case = no_moves_after_game_over
Input = Board:
wR . bK
bR . .
Commands:
click 50 50
click 250 50
wait 2000
click 50 150
click 150 150
wait 1000
print board
Output = . . wR
bR . .

Case = white_pawn_double_from_start_valid
Input = Board:
. . .
. . .
. . .
. wP .
Commands:
click 150 350
click 150 150
wait 2000
print board
Output = . . .
. wP .
. . .
. . .

Case = black_pawn_double_from_start_valid
Input = Board:
. bP .
. . .
. . .
. . .
Commands:
click 150 50
click 150 250
wait 2000
print board
Output = . . .
. . .
. bP .
. . .

Case = white_pawn_double_blocked_invalid
Input = Board:
. . .
. . .
. bR .
. wP .
Commands:
click 150 350
click 150 150
wait 2000
print board
Output = . . .
. . .
. bR .
. wP .

Case = white_pawn_double_from_non_start_invalid
Input = Board:
. . .
. . .
. wP .
. . .
Commands:
click 150 250
click 150 50
wait 2000
print board
Output = . . .
. . .
. wP .
. . .

Case = white_pawn_promotes_to_queen
Input = Board:
. . .
. wP .
Commands:
click 150 150
click 150 50
wait 1000
print board
Output = . wQ .
. . .

Case = black_pawn_promotes_to_queen
Input = Board:
. bP .
. . .
Commands:
click 150 50
click 150 150
wait 1000
print board
Output = . . .
. bQ .

Case = promoted_queen_moves_diagonal
Input = Board:
. . .
. wP .
. . .
Commands:
click 150 150
click 150 50
wait 2000
click 150 50
click 250 150
wait 1000
print board
Output = . . .
. . wQ
. . .

Case = jump_lands_same_square
Input = Board:
. . .
. wK .
. . .
Commands:
jump 150 150
wait 1000
print board
Output = . . .
. wK .
. . .

Case = airborne_piece_captures_arriving_enemy
Input = Board:
. . .
wK bR .
. . .
Commands:
jump 50 150
click 150 150
click 50 150
wait 1000
print board
Output = . . .
wK . .
. . .

Case = jump_too_late_does_not_save_piece
Input = Board:
. . .
wK bR .
. . .
Commands:
click 150 150
click 50 150
wait 1000
jump 50 150
print board
Output = . . .
bR . .
. . .

Case = enemy_arrives_after_landing_captures_normally
Input = Board:
. . . .
wK . . bR
. . . .
Commands:
jump 50 150
wait 1000
click 350 150
click 50 150
wait 3000
print board
Output = . . . .
bR . . .
. . . .

Case = cannot_jump_while_moving
Input = Board:
wR . .
Commands:
click 50 50
click 250 50
wait 500
jump 50 50
wait 1500
print board
Output = . . wR

Case = airborne_capture_only_enemy
Input = Board:
. . .
wK wR .
. . .
Commands:
jump 50 150
click 150 150
click 50 150
wait 1000
print board
Output = . . .
wK wR .
. . .
"""

def parse_cases():
    """מפרק את טקסט הבדיקות הגולמי למבנה נתונים מסודר ש-pytest יכול להריץ"""
    cases = []
    chunks = RAW_TESTS.strip().split("Case = ")
    for chunk in chunks:
        if not chunk:
            continue
        lines = chunk.strip().splitlines()
        name = lines[0].strip()
        
        # פיצול לפי קטעים
        text = "\n".join(lines[1:])
        input_part, output_part = text.split("Output =")
        
        # ניקוי המבוא של ה-Input
        input_str = input_part.replace("Input =", "").strip()
        # ניקוי גרשיים מיותרים מהפלט הצפוי אם יש
        expected_str = output_part.strip().strip('"')
        
        cases.append((name, input_str, expected_str))
    return cases

@pytest.mark.parametrize("name, input_data, expected_output", parse_cases())
def test_school_assignment_cases(name, input_data, expected_output, capsys):
    sys.stdin = io.StringIO(input_data + "\n")
    try:
        main()
    finally:
        sys.stdin = sys.__stdin__
        
    captured = capsys.readouterr()
    actual_lines = [line.strip() for line in captured.out.strip().splitlines() if line.strip()]
    expected_lines = [line.strip() for line in expected_output.strip().splitlines() if line.strip()]
    
    assert actual_lines == expected_lines, f"Failed case: {name}"