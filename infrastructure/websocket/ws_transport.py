"""infrastructure/websocket/ws_transport.py

Real WebSocket implementation of the ports/transport.py contract, wrapping
the `websockets` library. The websockets-specific ConnectionClosed exception
is translated to ports.transport.ConnectionClosed so callers (e.g.
server/connection_handler.py) don't need to depend on this library directly.
"""
from __future__ import annotations

import uuid
from typing import Awaitable, Callable

import websockets
from websockets.exceptions import ConnectionClosed as WsConnectionClosed

from ports.transport import Connection, ConnectionClosed, TransportServer


class WebSocketConnection(Connection):

    def __init__(self, websocket):
        self._ws = websocket
        self._id = uuid.uuid4().hex[:8]

    @property
    def connection_id(self) -> str:
        return self._id

    async def send(self, raw: str) -> None:
        try:
            await self._ws.send(raw)
        except WsConnectionClosed as exc:
            raise ConnectionClosed(str(exc)) from exc

    async def receive(self) -> str:
        try:
            return await self._ws.recv()
        except WsConnectionClosed as exc:
            raise ConnectionClosed(str(exc)) from exc

    async def close(self) -> None:
        await self._ws.close()


class WebSocketTransportServer(TransportServer):

    def __init__(self, host: str, port: int):
        self._host = host
        self._port = port
        self._server = None

    async def start(self, on_connect: Callable[[Connection], Awaitable[None]]) -> None:
        async def _handler(websocket, *_legacy_path) -> None:
            connection = WebSocketConnection(websocket)
            try:
                await on_connect(connection)
            except WsConnectionClosed:
                pass

        self._server = await websockets.serve(_handler, self._host, self._port)

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
