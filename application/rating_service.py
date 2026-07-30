"""application/rating_service.py

Pure, stateless ELO rating computation — no I/O, no persistence, no event
bus. K=32, standard expected-score formula.

This engine has no draw outcome: rules/game_conditions.py's
KingCaptureWinCondition only ever fires as the direct consequence of a
specific move capturing a king (see game/move_resolver.py's
_settle_move()) — there is no stalemate, timeout, or agreement-to-draw path
anywhere in the engine. So compute_new_ratings() only ever takes a decisive
winner; there is no draw-handling to build here.
"""
from __future__ import annotations

_K_FACTOR = 32


def _expected_score(own_rating: int, opponent_rating: int) -> float:
    return 1.0 / (1.0 + 10 ** ((opponent_rating - own_rating) / 400))


def compute_new_ratings(white_rating: int, black_rating: int, winner: str) -> tuple[int, int]:
    """Return (new_white_rating, new_black_rating) after one decisive game.

    winner must be "white" or "black" — there is no draw outcome to
    represent (see module docstring).
    """
    if winner not in ("white", "black"):
        raise ValueError(f"winner must be 'white' or 'black', got {winner!r}")

    white_actual = 1.0 if winner == "white" else 0.0
    black_actual = 1.0 - white_actual

    white_expected = _expected_score(white_rating, black_rating)
    black_expected = _expected_score(black_rating, white_rating)

    new_white = white_rating + _K_FACTOR * (white_actual - white_expected)
    new_black = black_rating + _K_FACTOR * (black_actual - black_expected)

    return round(new_white), round(new_black)
