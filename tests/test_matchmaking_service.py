import asyncio

from application.matchmaking_service import MatchmakingService


def run_async(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def make_counting_session_factory():
    """Fake session_factory: no real GameEngine/GameSession, just a
    deterministic, incrementing dummy session_id per call."""
    counter = {"n": 0}

    def factory(username_a: str, username_b: str) -> str:
        counter["n"] += 1
        return f"session-{counter['n']}"

    return factory


def test_two_players_within_rating_tolerance_get_matched_with_same_session():
    service = MatchmakingService(
        session_factory=make_counting_session_factory(), rating_tolerance=100, timeout_s=5.0)

    async def scenario():
        return await asyncio.gather(
            service.enqueue_and_wait("alice", 1200),
            service.enqueue_and_wait("bob", 1250),
        )

    result_alice, result_bob = run_async(scenario())

    assert result_alice.matched is True
    assert result_bob.matched is True
    assert result_alice.opponent_username == "bob"
    assert result_bob.opponent_username == "alice"
    assert result_alice.session_id is not None
    assert result_alice.session_id == result_bob.session_id


def test_lone_player_with_no_compatible_opponent_times_out():
    service = MatchmakingService(
        session_factory=make_counting_session_factory(), timeout_s=0.2)

    result = run_async(service.enqueue_and_wait("alice", 1200))

    assert result.matched is False
    assert result.opponent_username is None
    assert result.session_id is None


def test_players_outside_rating_tolerance_do_not_get_matched():
    service = MatchmakingService(
        session_factory=make_counting_session_factory(), rating_tolerance=100, timeout_s=0.2)

    async def scenario():
        return await asyncio.gather(
            service.enqueue_and_wait("alice", 1000),
            service.enqueue_and_wait("bob", 1300),
        )

    result_alice, result_bob = run_async(scenario())

    assert result_alice.matched is False
    assert result_bob.matched is False


def test_concurrent_enqueue_and_wait_resolves_correctly_for_both_sides():
    """Regression test for the 'who notices the match' race: two
    enqueue_and_wait() coroutines started together (asyncio.gather) for
    compatible players must both resolve to matched=True, with each other's
    username and the exact same session_id — never a deadlock, and never
    two different sessions created for the same pair."""
    service = MatchmakingService(
        session_factory=make_counting_session_factory(), rating_tolerance=100, timeout_s=5.0)

    async def scenario():
        return await asyncio.gather(
            service.enqueue_and_wait("carol", 1500),
            service.enqueue_and_wait("dave", 1450),
        )

    result_carol, result_dave = run_async(scenario())

    assert result_carol.matched is True
    assert result_dave.matched is True
    assert result_carol.opponent_username == "dave"
    assert result_dave.opponent_username == "carol"
    assert result_carol.session_id == result_dave.session_id
