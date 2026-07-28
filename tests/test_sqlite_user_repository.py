import asyncio
import sqlite3

import pytest

from infrastructure.persistence.sqlite_user_repository import SqliteUserRepository


def run_async(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def make_repository(tmp_path) -> SqliteUserRepository:
    # A real temp-file DB, not ":memory:": this repository opens a fresh
    # sqlite3.Connection per operation (see sqlite_user_repository.py's
    # module docstring), and separate connections to ":memory:" each get
    # their own independent, non-persistent database — a file is required
    # for state to survive across the create_user/find_by_username calls
    # below.
    db_path = str(tmp_path / "test_kfchess.db")
    repository = SqliteUserRepository(db_path)
    run_async(repository.ensure_schema())
    return repository


def test_create_user_then_find_by_username_round_trips(tmp_path):
    repository = make_repository(tmp_path)

    created = run_async(repository.create_user(
        username="alice", password_hash="deadbeef", salt="cafef00d",
    ))
    assert created.username == "alice"
    assert created.password_hash == "deadbeef"
    assert created.salt == "cafef00d"
    assert created.rating == 1200

    found = run_async(repository.find_by_username("alice"))
    assert found == created


def test_find_by_username_on_nonexistent_user_returns_none(tmp_path):
    repository = make_repository(tmp_path)

    assert run_async(repository.find_by_username("nobody")) is None


def test_create_user_with_duplicate_username_raises_integrity_error(tmp_path):
    repository = make_repository(tmp_path)
    run_async(repository.create_user(username="alice", password_hash="hash1", salt="salt1"))

    with pytest.raises(sqlite3.IntegrityError):
        run_async(repository.create_user(username="alice", password_hash="hash2", salt="salt2"))
