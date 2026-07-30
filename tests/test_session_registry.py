import asyncio

from infrastructure.bus.in_memory_bus import InMemoryEventBus
from server.session_registry import SessionRegistry


def run_async(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_create_session_starts_a_ticker_that_actually_advances_state():
    bus = InMemoryEventBus()
    registry = SessionRegistry(bus)
    received: list = []

    async def scenario():
        session_id = registry.create_session("alice", "bob")
        bus.subscribe(f"session:{session_id}", received.append)
        await asyncio.sleep(0.2)  # a handful of real ticks at SERVER_TICK_MS=50ms

    run_async(scenario())

    assert len(received) >= 2
    clocks = [event.clock_ms for event in received]
    assert clocks[-1] > clocks[0]


def test_get_session_retrieves_the_created_session():
    bus = InMemoryEventBus()
    registry = SessionRegistry(bus)

    async def scenario():
        return registry.create_session("alice", "bob")

    session_id = run_async(scenario())
    session = registry.get_session(session_id)

    assert session.session_id == session_id


def test_remove_session_cancels_its_ticker_task():
    bus = InMemoryEventBus()
    registry = SessionRegistry(bus)

    async def scenario():
        session_id = registry.create_session("alice", "bob")
        ticker_task = registry._ticker_tasks[session_id]

        registry.remove_session(session_id)
        await asyncio.sleep(0)  # let the cancellation actually propagate

        return session_id, ticker_task

    session_id, ticker_task = run_async(scenario())

    assert ticker_task.cancelled() or ticker_task.done()
    assert session_id not in registry._sessions
    assert session_id not in registry._ticker_tasks


def test_create_session_assigns_the_two_usernames_to_different_colors():
    bus = InMemoryEventBus()
    registry = SessionRegistry(bus)

    async def scenario():
        return registry.create_session("alice", "bob")

    session_id = run_async(scenario())
    players = registry.get_players(session_id)

    assert {players.white_username, players.black_username} == {"alice", "bob"}
    assert players.white_username != players.black_username


def test_create_session_assigns_colors_roughly_randomly():
    """Not a strict statistical test — just confirms both colorings are
    actually reachable (i.e. assignment isn't secretly hardcoded to always
    put username_a on one particular color), by running enough trials that
    getting the same coloring every time would be a ~1-in-2^30 fluke."""
    bus = InMemoryEventBus()
    registry = SessionRegistry(bus)

    async def scenario():
        return [registry.create_session("alice", "bob") for _ in range(30)]

    session_ids = run_async(scenario())
    colorings = {
        registry.get_players(session_id).white_username for session_id in session_ids
    }

    assert colorings == {"alice", "bob"}


def test_remove_session_also_drops_the_players_mapping():
    bus = InMemoryEventBus()
    registry = SessionRegistry(bus)

    async def scenario():
        return registry.create_session("alice", "bob")

    session_id = run_async(scenario())
    registry.remove_session(session_id)

    assert session_id not in registry._players
