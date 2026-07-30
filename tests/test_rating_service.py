import pytest

from application.rating_service import compute_new_ratings


def test_equal_ratings_white_wins_moves_both_by_the_same_amount_in_opposite_directions():
    new_white, new_black = compute_new_ratings(white_rating=1200, black_rating=1200, winner="white")

    assert new_white == 1216
    assert new_black == 1184
    assert (new_white - 1200) == -(new_black - 1200)


def test_equal_ratings_black_wins_moves_both_by_the_same_amount_in_opposite_directions():
    new_white, new_black = compute_new_ratings(white_rating=1200, black_rating=1200, winner="black")

    assert new_white == 1184
    assert new_black == 1216


def test_big_rating_gap_underdog_win_produces_a_larger_swing_than_favorite_winning():
    # White (1200) is a heavy underdog against black (1800).
    underdog_new_white, underdog_new_black = compute_new_ratings(
        white_rating=1200, black_rating=1800, winner="white")
    underdog_swing = underdog_new_white - 1200

    # Same pairing, but the favorite (black) wins instead.
    favorite_new_white, favorite_new_black = compute_new_ratings(
        white_rating=1200, black_rating=1800, winner="black")
    favorite_swing = favorite_new_black - 1800

    assert underdog_swing > favorite_swing
    assert underdog_swing == 31
    assert favorite_swing == 1
    # Zero-sum: whatever one side gains, the other loses.
    assert (underdog_new_white - 1200) == -(underdog_new_black - 1800)
    assert (favorite_new_black - 1800) == -(favorite_new_white - 1200)


def test_compute_new_ratings_raises_on_a_non_decisive_winner():
    # This engine has no draw outcome (see application/rating_service.py's
    # module docstring) — "draw", "none", or anything other than "white"/
    # "black" is a contract violation, not a valid input to half-handle.
    with pytest.raises(ValueError):
        compute_new_ratings(white_rating=1200, black_rating=1200, winner="draw")

    with pytest.raises(ValueError):
        compute_new_ratings(white_rating=1200, black_rating=1200, winner=None)
