import asyncio

from application.rating_service import compute_new_ratings
from application.rating_update_service import RatingUpdateService
from infrastructure.bus.in_memory_bus import InMemoryEventBus
from ports.user_repository import UserRecord, UserRepository
from protocol.messages import GameStateEvent
from server.session_registry import SessionPlayers


class FakeUserRepository(UserRepository):
    """Dict-backed in-memory UserRepository — no real SQLite."""

    def __init__(self, ratings: dict = None):
        self._users: dict = {
            username: UserRecord(username=username, password_hash="x", salt="y", rating=rating)
            for username, rating in (ratings or {}).items()
        }
        self.update_rating_calls = 0

    async def find_by_username(self, username):
        return self._users.get(username)

    async def create_user(self, username, password_hash, salt):
        record = UserRecord(username=username, password_hash=password_hash, salt=salt, rating=1200)
        self._users[username] = record
        return record

    async def update_rating(self, username: str, new_rating: int) -> None:
        self.update_rating_calls += 1
        record = self._users[username]
        self._users[username] = UserRecord(
            username=record.username, password_hash=record.password_hash,
            salt=record.salt, rating=new_rating,
        )


class FlakyUserRepository(FakeUserRepository):
    """Same as FakeUserRepository, but update_rating raises for every call
    while should_fail is True — lets a test simulate a DB outage and then
    flip it off to prove a later retry succeeds."""

    def __init__(self, ratings: dict = None):
        super().__init__(ratings)
        self.should_fail = False

    async def update_rating(self, username: str, new_rating: int) -> None:
        if self.should_fail:
            self.update_rating_calls += 1
            raise RuntimeError("simulated DB failure")
        await super().update_rating(username, new_rating)


class FakeSessionRegistry:
    """Just enough of SessionRegistry.get_players() for this service —
    no real session/engine/ticker involved."""

    def __init__(self, players_by_session: dict):
        self._players_by_session = players_by_session

    def get_players(self, session_id: str):
        return self._players_by_session[session_id]


class NullLogger:
    def info(self, *args, **kwargs):
        pass

    def warning(self, *args, **kwargs):
        pass


def _game_over_event(winner: str) -> GameStateEvent:
    return GameStateEvent(
        clock_ms=1000.0, board_tokens=(), board_height=0, board_width=0,
        active_moves=(), active_jumps=(), selected_cell=None,
        game_over=True, winner=winner, empty_token=".",
    )


def _in_progress_event() -> GameStateEvent:
    return GameStateEvent(
        clock_ms=500.0, board_tokens=(), board_height=0, board_width=0,
        active_moves=(), active_jumps=(), selected_cell=None,
        game_over=False, winner=None, empty_token=".",
    )


def run_async(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_game_over_event_updates_both_players_ratings_correctly():
    repository = FakeUserRepository({"alice": 1200, "bob": 1400})
    registry = FakeSessionRegistry({
        "s1": SessionPlayers(white_username="alice", black_username="bob"),
    })
    bus = InMemoryEventBus()
    service = RatingUpdateService(bus, repository, registry, NullLogger())
    service.subscribe_to("s1")

    async def scenario():
        bus.publish("session:s1", _game_over_event(winner="white"))
        await asyncio.sleep(0.05)  # let the scheduled task run

    run_async(scenario())

    expected_white, expected_black = compute_new_ratings(
        white_rating=1200, black_rating=1400, winner="white")

    alice = run_async(repository.find_by_username("alice"))
    bob = run_async(repository.find_by_username("bob"))
    assert alice.rating == expected_white
    assert bob.rating == expected_black


def test_non_game_over_event_does_not_touch_ratings():
    repository = FakeUserRepository({"alice": 1200, "bob": 1400})
    registry = FakeSessionRegistry({
        "s1": SessionPlayers(white_username="alice", black_username="bob"),
    })
    bus = InMemoryEventBus()
    service = RatingUpdateService(bus, repository, registry, NullLogger())
    service.subscribe_to("s1")

    async def scenario():
        bus.publish("session:s1", _in_progress_event())
        await asyncio.sleep(0.05)

    run_async(scenario())

    alice = run_async(repository.find_by_username("alice"))
    bob = run_async(repository.find_by_username("bob"))
    assert alice.rating == 1200
    assert bob.rating == 1400


def test_duplicate_game_over_events_for_the_same_session_only_update_ratings_once():
    repository = FakeUserRepository({"alice": 1200, "bob": 1400})
    registry = FakeSessionRegistry({
        "s1": SessionPlayers(white_username="alice", black_username="bob"),
    })
    bus = InMemoryEventBus()
    service = RatingUpdateService(bus, repository, registry, NullLogger())
    service.subscribe_to("s1")

    async def scenario():
        bus.publish("session:s1", _game_over_event(winner="white"))
        await asyncio.sleep(0.05)
        first_alice = await repository.find_by_username("alice")
        first_bob = await repository.find_by_username("bob")

        # A duplicate broadcast of the same game-over outcome for the same
        # session — must be a no-op, not a second rating update on top of
        # the first.
        bus.publish("session:s1", _game_over_event(winner="white"))
        await asyncio.sleep(0.05)
        second_alice = await repository.find_by_username("alice")
        second_bob = await repository.find_by_username("bob")

        return first_alice.rating, first_bob.rating, second_alice.rating, second_bob.rating

    first_alice_rating, first_bob_rating, second_alice_rating, second_bob_rating = \
        run_async(scenario())

    assert second_alice_rating == first_alice_rating
    assert second_bob_rating == first_bob_rating


def test_failed_update_does_not_mark_session_handled_so_a_later_event_retries():
    repository = FlakyUserRepository({"alice": 1200, "bob": 1400})
    repository.should_fail = True
    registry = FakeSessionRegistry({
        "s1": SessionPlayers(white_username="alice", black_username="bob"),
    })
    bus = InMemoryEventBus()
    service = RatingUpdateService(bus, repository, registry, NullLogger())
    service.subscribe_to("s1")

    async def scenario():
        bus.publish("session:s1", _game_over_event(winner="white"))
        await asyncio.sleep(0.05)
        calls_after_failure = repository.update_rating_calls

        # "Fix the outage" and let a duplicate broadcast retry — this only
        # produces a real second attempt if the failed first attempt never
        # marked the session as handled.
        repository.should_fail = False
        bus.publish("session:s1", _game_over_event(winner="white"))
        await asyncio.sleep(0.05)

        return calls_after_failure, repository.update_rating_calls

    calls_after_failure, calls_after_retry = run_async(scenario())

    assert calls_after_failure >= 1                  # the failing attempt really ran
    assert calls_after_retry > calls_after_failure    # a genuine second attempt happened

    expected_white, expected_black = compute_new_ratings(
        white_rating=1200, black_rating=1400, winner="white")
    alice = run_async(repository.find_by_username("alice"))
    bob = run_async(repository.find_by_username("bob"))
    assert alice.rating == expected_white
    assert bob.rating == expected_black


def test_two_back_to_back_game_over_events_with_no_yield_result_in_exactly_one_update():
    """Regression test for the check-then-mark race: two duplicate
    game_over broadcasts published synchronously, back-to-back, with no
    await in between — before either _apply_rating_update task has had a
    chance to run past the lock's re-check — must still result in exactly
    one successful update, not two racing concurrent ones (which would
    either double-apply the rating change or corrupt it via interleaved
    reads/writes)."""
    repository = FakeUserRepository({"alice": 1200, "bob": 1400})
    registry = FakeSessionRegistry({
        "s1": SessionPlayers(white_username="alice", black_username="bob"),
    })
    bus = InMemoryEventBus()
    service = RatingUpdateService(bus, repository, registry, NullLogger())
    service.subscribe_to("s1")

    async def scenario():
        # Both publishes happen synchronously, back-to-back — each only
        # schedules an asyncio.create_task; neither has actually run yet by
        # the time the second publish() call happens.
        bus.publish("session:s1", _game_over_event(winner="white"))
        bus.publish("session:s1", _game_over_event(winner="white"))
        await asyncio.sleep(0.05)

    run_async(scenario())

    expected_white, expected_black = compute_new_ratings(
        white_rating=1200, black_rating=1400, winner="white")
    alice = run_async(repository.find_by_username("alice"))
    bob = run_async(repository.find_by_username("bob"))
    assert alice.rating == expected_white
    assert bob.rating == expected_black
    # One successful update touches update_rating exactly twice (white and
    # black); a second, racing update would double this to four.
    assert repository.update_rating_calls == 2
