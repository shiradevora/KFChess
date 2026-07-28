from __future__ import annotations

import asyncio

from application.auth_service import AuthService
from ports.user_repository import UserRecord, UserRepository


class FakeUserRepository(UserRepository):
    """Dict-backed in-memory UserRepository — no real SQLite."""

    def __init__(self):
        self._users: dict[str, UserRecord] = {}

    async def find_by_username(self, username: str) -> UserRecord | None:
        return self._users.get(username)

    async def create_user(self, username: str, password_hash: str, salt: str) -> UserRecord:
        record = UserRecord(username=username, password_hash=password_hash, salt=salt, rating=1200)
        self._users[username] = record
        return record


def run_async(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_register_with_new_username_succeeds_and_is_retrievable():
    service = AuthService(FakeUserRepository())

    result = run_async(service.register("alice", "hunter2"))

    assert result.success is True
    assert result.error is None

    stored = run_async(service._user_repository.find_by_username("alice"))
    assert stored is not None
    assert stored.username == "alice"


def test_register_with_existing_username_fails():
    repository = FakeUserRepository()
    service = AuthService(repository)
    run_async(service.register("alice", "hunter2"))

    result = run_async(service.register("alice", "different_password"))

    assert result.success is False
    assert result.error == "Username already taken"


def test_register_with_empty_username_fails():
    service = AuthService(FakeUserRepository())

    result = run_async(service.register("", "hunter2"))

    assert result.success is False
    assert result.error == "Username cannot be empty"


def test_login_with_correct_credentials_succeeds():
    repository = FakeUserRepository()
    service = AuthService(repository)
    run_async(service.register("alice", "hunter2"))

    result = run_async(service.login("alice", "hunter2"))

    assert result.success is True
    assert result.error is None


def test_login_with_unknown_username_fails_with_generic_message():
    service = AuthService(FakeUserRepository())

    result = run_async(service.login("nobody", "hunter2"))

    assert result.success is False
    assert result.error == "Invalid username or password"


def test_login_with_wrong_password_fails_with_same_generic_message():
    """Regression test locking in the username-enumeration mitigation: the
    failure message for 'unknown username' and 'wrong password' must be
    byte-for-byte identical, so a client can never tell them apart."""
    repository = FakeUserRepository()
    service = AuthService(repository)
    run_async(service.register("alice", "hunter2"))

    unknown_user_result = run_async(service.login("nobody", "hunter2"))
    wrong_password_result = run_async(service.login("alice", "wrong_password"))

    assert unknown_user_result.success is False
    assert wrong_password_result.success is False
    assert unknown_user_result.error == wrong_password_result.error == "Invalid username or password"
