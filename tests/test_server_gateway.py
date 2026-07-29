import asyncio

from infrastructure.bus.in_memory_bus import InMemoryEventBus
from ports.transport import Connection, ConnectionClosed
from protocol.codec import encode
from protocol.messages import ClickCommand, ErrorMessage, GameStateEvent
from client.server_gateway import SERVER_EVENTS_TOPIC, ServerGateway


class FakeConnection(Connection):
    """In-memory Connection backed by an asyncio Queue — no real socket,
    same style as tests/test_connection_handler.py's fake."""

    def __init__(self, connection_id="fake-1"):
        self._id = connection_id
        self.inbound = asyncio.Queue()
        self.outbound: list = []

    @property
    def connection_id(self) -> str:
        return self._id

    async def send(self, raw: str) -> None:
        self.outbound.append(raw)

    async def receive(self) -> str:
        item = await self.inbound.get()
        if item is None:
            raise ConnectionClosed("closed by test")
        return item

    async def close(self) -> None:
        pass


class NullLogger:
    def info(self, *args, **kwargs):
        pass

    def warning(self, *args, **kwargs):
        pass


def _game_state_event(clock_ms: float = 1.0) -> GameStateEvent:
    return GameStateEvent(
        clock_ms=clock_ms,
        board_tokens=(),
        board_height=0,
        board_width=0,
        active_moves=(),
        active_jumps=(),
        selected_cell=None,
        game_over=False,
        empty_token=".",
    )


def run_async(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_pump_messages_decodes_and_publishes_game_state_event():
    bus = InMemoryEventBus()
    received = []
    bus.subscribe(SERVER_EVENTS_TOPIC, received.append)

    gateway = ServerGateway("localhost", 0, bus, NullLogger())
    connection = FakeConnection()
    event = _game_state_event()

    async def scenario():
        await connection.inbound.put(encode(event))
        await connection.inbound.put(None)  # signal close
        await gateway._pump_messages(connection)

    run_async(scenario())

    assert received == [event]


def test_pump_messages_decodes_and_publishes_error_message():
    bus = InMemoryEventBus()
    received = []
    bus.subscribe(SERVER_EVENTS_TOPIC, received.append)

    gateway = ServerGateway("localhost", 0, bus, NullLogger())
    connection = FakeConnection()

    async def scenario():
        await connection.inbound.put(encode(ErrorMessage(message="illegal move")))
        await connection.inbound.put(None)
        await gateway._pump_messages(connection)

    run_async(scenario())

    assert received == [ErrorMessage(message="illegal move")]


def test_pump_messages_skips_malformed_json_and_keeps_processing():
    bus = InMemoryEventBus()
    received = []
    bus.subscribe(SERVER_EVENTS_TOPIC, received.append)

    gateway = ServerGateway("localhost", 0, bus, NullLogger())
    connection = FakeConnection()
    event = _game_state_event(clock_ms=2.0)

    async def scenario():
        await connection.inbound.put("{not valid json")
        await connection.inbound.put(encode(event))
        await connection.inbound.put(None)
        await gateway._pump_messages(connection)

    run_async(scenario())

    # The malformed message didn't kill the loop: the later, valid message
    # still made it through.
    assert received == [event]


def test_pump_messages_returns_cleanly_on_connection_closed():
    bus = InMemoryEventBus()
    gateway = ServerGateway("localhost", 0, bus, NullLogger())
    connection = FakeConnection()

    async def scenario():
        await connection.inbound.put(None)  # closed immediately
        await gateway._pump_messages(connection)  # must not raise

    run_async(scenario())


def test_send_click_and_send_jump_are_no_ops_before_connect():
    # Guards against a crash if the render loop calls handle_click/handle_jump
    # before the background connection is actually established.
    bus = InMemoryEventBus()
    gateway = ServerGateway("localhost", 0, bus, NullLogger())

    gateway.send_click(10, 20)
    gateway.send_jump(30, 40)


def test_send_credentials_login_and_send_register_are_no_ops_before_connect():
    bus = InMemoryEventBus()
    gateway = ServerGateway("localhost", 0, bus, NullLogger())

    gateway.send_credentials_login("alice", "hunter2")
    gateway.send_register("bob", "hunter3")
    gateway.send_play()


def test_rapid_back_to_back_sends_are_both_delivered_in_order_not_dropped():
    """Regression test for the run_coroutine_threadsafe-per-send race: two
    outgoing commands enqueued back-to-back, before the writer has had a
    chance to drain the first one, must still result in two separate,
    in-order send() calls — not interleaved or dropped."""
    bus = InMemoryEventBus()
    gateway = ServerGateway("localhost", 0, bus, NullLogger())
    connection = FakeConnection()

    async def scenario():
        gateway._loop = asyncio.get_event_loop()
        gateway._outbox = asyncio.Queue()
        gateway._connection = connection

        writer_task = asyncio.ensure_future(gateway._writer(connection))

        # Two sends with no await in between — exactly the double-click /
        # same-frame pattern that used to race two concurrent send() calls.
        gateway.send_click(1, 2)
        gateway.send_jump(3, 4)

        await asyncio.sleep(0.05)
        writer_task.cancel()
        try:
            await writer_task
        except asyncio.CancelledError:
            pass

    run_async(scenario())

    assert len(connection.outbound) == 2
    first, second = connection.outbound
    assert '"type": "click"' in first
    assert '"type": "jump"' in second


def test_rapid_back_to_back_sends_including_login_are_delivered_in_order():
    """Same regression coverage as above, extended to send_credentials_login:
    it must go through the same _outbox queue/writer path as send_click/
    send_jump, not a separate direct send — otherwise it could race with
    them."""
    bus = InMemoryEventBus()
    gateway = ServerGateway("localhost", 0, bus, NullLogger())
    connection = FakeConnection()

    async def scenario():
        gateway._loop = asyncio.get_event_loop()
        gateway._outbox = asyncio.Queue()
        gateway._connection = connection

        writer_task = asyncio.ensure_future(gateway._writer(connection))

        gateway.send_credentials_login("alice", "hunter2")
        gateway.send_click(1, 2)
        gateway.send_jump(3, 4)

        await asyncio.sleep(0.05)
        writer_task.cancel()
        try:
            await writer_task
        except asyncio.CancelledError:
            pass

    run_async(scenario())

    assert len(connection.outbound) == 3
    first, second, third = connection.outbound
    assert '"type": "login"' in first
    assert '"type": "click"' in second
    assert '"type": "jump"' in third


def test_rapid_back_to_back_send_register_is_delivered_through_same_writer():
    """Same regression coverage, for send_register."""
    bus = InMemoryEventBus()
    gateway = ServerGateway("localhost", 0, bus, NullLogger())
    connection = FakeConnection()

    async def scenario():
        gateway._loop = asyncio.get_event_loop()
        gateway._outbox = asyncio.Queue()
        gateway._connection = connection

        writer_task = asyncio.ensure_future(gateway._writer(connection))

        gateway.send_register("alice", "hunter2")
        gateway.send_click(1, 2)

        await asyncio.sleep(0.05)
        writer_task.cancel()
        try:
            await writer_task
        except asyncio.CancelledError:
            pass

    run_async(scenario())

    assert len(connection.outbound) == 2
    first, second = connection.outbound
    assert '"type": "register"' in first
    assert '"type": "click"' in second


def test_rapid_back_to_back_send_play_is_delivered_through_same_writer():
    """Same regression coverage, for send_play."""
    bus = InMemoryEventBus()
    gateway = ServerGateway("localhost", 0, bus, NullLogger())
    connection = FakeConnection()

    async def scenario():
        gateway._loop = asyncio.get_event_loop()
        gateway._outbox = asyncio.Queue()
        gateway._connection = connection

        writer_task = asyncio.ensure_future(gateway._writer(connection))

        gateway.send_play()
        gateway.send_click(1, 2)

        await asyncio.sleep(0.05)
        writer_task.cancel()
        try:
            await writer_task
        except asyncio.CancelledError:
            pass

    run_async(scenario())

    assert len(connection.outbound) == 2
    first, second = connection.outbound
    assert '"type": "play"' in first
    assert '"type": "click"' in second
