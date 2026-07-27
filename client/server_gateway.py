"""client/server_gateway.py

ServerGateway — the client-side mirror of server/connection_handler.py.

It owns a background thread running its own asyncio event loop that holds
the single websocket Connection, so the rest of the client (a synchronous
cv2 render loop) never has to touch asyncio directly: sending a command is
a plain synchronous method call, and inbound server messages arrive on the
EventBus, decoupled from whichever thread is actually reading the socket.
"""
from __future__ import annotations

import asyncio
import threading
from typing import Any

import websockets

from infrastructure.websocket.ws_transport import WebSocketConnection
from ports.event_bus import EventBus
from ports.transport import Connection, ConnectionClosed
from protocol.codec import DecodeError, decode, encode
from protocol.messages import ClickCommand, JumpCommand

SERVER_EVENTS_TOPIC = "server_events"


class ServerGateway:

    def __init__(self, host: str, port: int, event_bus: EventBus, logger):
        self._host = host
        self._port = port
        self._event_bus = event_bus
        self._logger = logger

        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._connection: Connection | None = None
        self._serve_task: asyncio.Task | None = None
        self._writer_task: asyncio.Task | None = None
        self._outbox: asyncio.Queue | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def connect(self, timeout_s: float = 5.0) -> None:
        ready = threading.Event()
        error: list[BaseException] = []

        self._thread = threading.Thread(
            target=self._run_loop, args=(ready, error), daemon=True
        )
        self._thread.start()

        if not ready.wait(timeout_s):
            raise ConnectionError(
                f"could not reach ws://{self._host}:{self._port} — is server_app.py running?"
            )
        if error:
            raise ConnectionError(
                f"could not reach ws://{self._host}:{self._port} — is server_app.py running?"
            ) from error[0]

    def close(self) -> None:
        if self._loop is None:
            return

        async def _shutdown() -> None:
            if self._connection is not None:
                try:
                    await self._connection.close()
                except Exception:  # noqa: BLE001 - best-effort on the way out
                    pass
            if self._serve_task is not None:
                self._serve_task.cancel()
                try:
                    await self._serve_task
                except (asyncio.CancelledError, Exception):
                    pass
            if self._writer_task is not None:
                self._writer_task.cancel()
                try:
                    await self._writer_task
                except asyncio.CancelledError:
                    pass

        future = asyncio.run_coroutine_threadsafe(_shutdown(), self._loop)
        try:
            future.result(timeout=2.0)
        except Exception:  # noqa: BLE001 - best-effort on the way out
            pass

        self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    # ------------------------------------------------------------------
    # Outbound commands (called from the main/cv2 thread)
    # ------------------------------------------------------------------

    def send_click(self, x: int, y: int) -> None:
        self._send(ClickCommand(x=x, y=y))

    def send_jump(self, x: int, y: int) -> None:
        self._send(JumpCommand(x=x, y=y))

    def _send(self, command: Any) -> None:
        if self._loop is None or self._outbox is None:
            return
        # call_soon_threadsafe (not run_coroutine_threadsafe) is correct here:
        # put_nowait is synchronous, so we're just safely handing the queue a
        # new item from the other thread, not running a coroutine. The actual
        # send happens sequentially on the background loop via _writer(), so
        # rapid back-to-back calls from the main thread can never race two
        # concurrent send() calls on the same connection.
        self._loop.call_soon_threadsafe(self._outbox.put_nowait, encode(command))

    # ------------------------------------------------------------------
    # Background event loop thread
    # ------------------------------------------------------------------

    def _run_loop(self, ready: threading.Event, error: list) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        self._outbox = asyncio.Queue()
        self._serve_task = loop.create_task(self._connect_and_serve(ready, error))
        try:
            loop.run_forever()
        finally:
            loop.close()

    async def _connect_and_serve(self, ready: threading.Event, error: list) -> None:
        try:
            websocket = await websockets.connect(f"ws://{self._host}:{self._port}")
        except Exception as exc:  # noqa: BLE001 - surfaced to the main thread via `error`
            error.append(exc)
            ready.set()
            return

        self._connection = WebSocketConnection(websocket)
        ready.set()

        self._writer_task = asyncio.create_task(self._writer(self._connection))
        await self._pump_messages(self._connection)

    async def _writer(self, connection: Connection) -> None:
        """Single dedicated writer for this connection: drains the outbox
        one item at a time, so sends triggered by rapid-fire send_click/
        send_jump calls from the main thread are always sequential — never
        two concurrent send() calls racing on the same connection."""
        while True:
            raw = await self._outbox.get()
            try:
                await connection.send(raw)
            except ConnectionClosed:
                self._logger.info("Server connection closed while writing")
                return

    async def _pump_messages(self, connection: Connection) -> None:
        """Receive loop: decode each inbound message and publish it on the
        bus for RemoteGameEngine (or anything else) to consume. Split out
        from _connect_and_serve so it can be exercised directly in tests
        with a fake Connection, without a real socket or background thread.
        """
        while True:
            try:
                raw = await connection.receive()
            except ConnectionClosed:
                self._logger.info("Server connection closed")
                return

            try:
                message = decode(raw)
            except DecodeError as exc:
                self._logger.warning("Malformed message from server: %s", exc)
                continue

            self._event_bus.publish(SERVER_EVENTS_TOPIC, message)
