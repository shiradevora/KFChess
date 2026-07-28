from gui.board_renderer import BoardRenderer


def test_frame_size_computes_pixel_dimensions():
    assert BoardRenderer.frame_size(8, 8, 60) == (480, 480)


def test_frame_size_handles_non_square_boards():
    assert BoardRenderer.frame_size(8, 4, 60) == (480, 240)
