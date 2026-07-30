import threading
import time

from client.remote_engine import RemoteGameEngine, SERVER_EVENTS_TOPIC
from config import settings
from board.text_board import TextBoardRepresentation
from game.engine import GameEngine
from infrastructure.bus.in_memory_bus import InMemoryEventBus
from ports.game_engine_port import GameEnginePort, SelfTicking
from protocol.messages import GameStateEvent
from rules.game_conditions import KingCaptureWinCondition, LastRankPromotion
from rules.rule_registry import build_default_registry


class FakeGateway:
    def send_click(self, x, y):
        pass

    def send_jump(self, x, y):
        pass


def test_game_engine_conforms_to_game_engine_port():
    board = TextBoardRepresentation([["wK", "."], [".", "."]])
    engine = GameEngine(
        board=board,
        rule_registry=build_default_registry(settings),
        win_condition=KingCaptureWinCondition(),
        promotion_rule=LastRankPromotion(),
        config=settings,
    )
    assert isinstance(engine, GameEnginePort)
    assert isinstance(engine, SelfTicking)


def test_remote_game_engine_conforms_to_game_engine_port():
    bus = InMemoryEventBus()
    event = GameStateEvent(
        clock_ms=0.0,
        board_tokens=(("wK", "."), (".", ".")),
        board_height=2, board_width=2,
        active_moves=(), active_jumps=(),
        selected_cell=None, game_over=False,
        winner=None,
        empty_token=".",
    )

    def _publish():
        time.sleep(0.05)
        bus.publish(SERVER_EVENTS_TOPIC, event)

    threading.Thread(target=_publish, daemon=True).start()

    engine = RemoteGameEngine(FakeGateway(), bus, initial_state_timeout_s=2.0)
    assert isinstance(engine, GameEnginePort)
    assert isinstance(engine, SelfTicking) is False
