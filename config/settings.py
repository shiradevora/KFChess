"""Central configuration for KungFu Chess.

All game constants live here so game logic never hardcodes magic numbers.
Changing timing, supported colors, or pawn starting rows only requires
editing this file - no other module should contain literal values like
these.
"""

# Rendering / timing (milliseconds)
CELL_SIZE = 100
MOVE_DURATION   = 1000   # base travel time for a 1-square move
JUMP_DURATION   = 1000
SHORT_COOLDOWN_MS = 500  # rest after a jump move
LONG_COOLDOWN_MS  = 1000 # rest after any non-jump move


def move_duration(start: tuple, end: tuple) -> float:
    """Return travel time in ms proportional to Chebyshev distance."""
    dist = max(abs(end[0] - start[0]), abs(end[1] - start[1]))
    return max(dist, 1) * MOVE_DURATION

# Player colors supported by the game
COLORS = ("w", "b")

# Row delta a pawn advances by on a single step, per color
PAWN_DIRECTION = {"w": -1, "b": 1}

# Starting row (0-indexed) from which each color's pawns may take a double step
PAWN_START_ROW = {"w": 6, "b": 1}

# Token used to represent an empty cell on the board
EMPTY_CELL = "."
