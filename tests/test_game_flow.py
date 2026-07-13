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
wK bK
. .
Commands:
print board
""",
        capsys,
    )
    assert output.out.splitlines() == ["wK bK", ". ."]


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
wK bK
wK
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
click 0 0
print board
""",
        capsys,
    )
    assert output.out.splitlines() == ["wR .", ". ."]