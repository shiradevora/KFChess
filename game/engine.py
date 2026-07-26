from game.move_resolver import MoveResolver
from game.input_handler import InputHandler


class GameEngine:
    def __init__(self, board, rule_registry, win_condition, promotion_rule, config):
        self._board = board
        self._resolver = MoveResolver(board, win_condition, promotion_rule, config)
        self._input = InputHandler(board, rule_registry, self._resolver, config)
        self._clock = 0

    @property
    def game_over(self):
        return self._resolver.game_over

    @property
    def clock(self):
        return self._clock

    @property
    def selected(self):
        return self._input.selected

    def wait(self, dt):
        self._clock += dt
        self._resolver.resolve(self._clock)

    def render(self, renderer):
        self._resolver.resolve(self._clock)
        return renderer.render(self._board)

    def handle_click(self, x, y):
        self._resolver.resolve(self._clock)
        if self._resolver.game_over:
            return
        self._input.handle_click(x, y, self._clock)

    def handle_jump(self, x, y):
        self._resolver.resolve(self._clock)
        if self._resolver.game_over:
            return
        self._input.handle_jump(x, y, self._clock)
