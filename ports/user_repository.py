"""ports/user_repository.py

Port for user persistence, implemented by a concrete adapter
(infrastructure/persistence/sqlite_user_repository.py) and consumed by
application/auth_service.py. UserRecord is the domain-level shape this port
returns — it is NOT a wire DTO (see protocol/messages.py) and must never
cross the network boundary directly.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class UserRecord:
    username: str
    password_hash: str
    salt: str
    rating: int


class UserRepository(ABC):

    @abstractmethod
    async def find_by_username(self, username: str) -> UserRecord | None:
        raise NotImplementedError

    @abstractmethod
    async def create_user(self, username: str, password_hash: str, salt: str) -> UserRecord:
        raise NotImplementedError
