"""ports/transport.py

Transport contract for exchanging wire messages (see protocol/messages.py)
with a remote peer over some byte-stream connection. Kept generic — no
mention of WebSockets, sockets, or any concrete transport here — so a real
implementation (infrastructure/websocket/ws_transport.py) and a fake one
(used in tests) can both satisfy the same contract.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Awaitable, Callable


class ConnectionClosed(Exception):
    """Raised by Connection.send()/receive() once the underlying connection has closed."""


class Connection(ABC):

    @property
    @abstractmethod
    def connection_id(self) -> str:
        raise NotImplementedError

    @abstractmethod
    async def send(self, raw: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def receive(self) -> str:
        """Return the next inbound message, or raise ConnectionClosed."""
        raise NotImplementedError

    @abstractmethod
    async def close(self) -> None:
        raise NotImplementedError


class TransportServer(ABC):

    @abstractmethod
    async def start(self, on_connect: Callable[[Connection], Awaitable[None]]) -> None:
        raise NotImplementedError

    @abstractmethod
    async def stop(self) -> None:
        raise NotImplementedError
