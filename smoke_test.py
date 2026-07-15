from gui.asset_loader import Assets
from gui.board_renderer import BoardRenderer
from config import settings

assets = Assets(settings.CELL_SIZE)
renderer = BoardRenderer(assets, 8, 8)

snapshot = [
    "bR bN bB bQ bK bB bN bR".split(),
    "bP bP bP bP bP bP bP bP".split(),
    ". . . . . . . .".split(),
    ". . . . . . . .".split(),
    ". . . . . . . .".split(),
    ". . . . . . . .".split(),
    "wP wP wP wP wP wP wP wP".split(),
    "wR wN wB wQ wK wB wN wR".split(),
]

frame = renderer.render(snapshot, ".", 0, (6, 4), [], [])
print("frame shape:", frame.shape, "— OK")
