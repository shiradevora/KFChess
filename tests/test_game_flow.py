import io
import sys

from main import main


def run_main(input_text, capsys):
    sys.stdin = io.StringIO(input_text)
    try:
        main()
    finally:
        sys.stdin = sys.__stdin__
    return capsys.readouterr()


def test_print_board_outputs_canonical_board(capsys):
    output = run_main(
        """Board:
8 8 8
.
Commands:
print board
""",
        capsys,
    )
    assert output.out.splitlines() == ["8 8 8", "."]


def test_unknown_token_returns_error(capsys):
    output = run_main(
        """Board:
X
Commands:
print board
""",
        capsys,
    )
    assert output.out.strip() == "ERROR UNKNOWN_TOKEN"


def test_row_width_mismatch_returns_error(capsys):
    output = run_main(
        """Board:
1 2
3
Commands:
print board
""",
        capsys,
    )
    assert output.out.strip() == "ERROR ROW_WIDTH_MISMATCH"


def test_click_moves_piece(capsys):
    output = run_main(
        """Board:
wR .
. .
Commands:
click 0 0
click 0 1
print board
""",
        capsys,
    )
    assert output.out.splitlines() == [". wR", ". ."]
