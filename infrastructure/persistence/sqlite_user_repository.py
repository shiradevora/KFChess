"""infrastructure/persistence/sqlite_user_repository.py

SQLite-backed UserRepository, built on the stdlib `sqlite3` module (a
synchronous driver) rather than aiosqlite. Every public method is `async
def`, but internally wraps its actual sqlite3 call in
`await loop.run_in_executor(None, ...)` so the blocking I/O never runs on
the asyncio event loop thread — callers (AuthService, connection_handler.py)
only ever see an async interface and don't need to know the driver
underneath is synchronous.

Connection strategy: each operation opens and closes its own short-lived
sqlite3.Connection inside the executor call, rather than holding one shared
connection across calls. sqlite3 connections aren't safe to use from a
thread other than the one that created them (without
check_same_thread=False), and run_in_executor's default ThreadPoolExecutor
may run different calls on different worker threads — a fresh per-call
connection sidesteps that entirely, and the per-connection overhead is
negligible at this project's request volume.
"""
from __future__ import annotations

import asyncio
import functools
import os
import sqlite3
from datetime import datetime, timezone

from ports.user_repository import UserRecord, UserRepository

_SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")


class SqliteUserRepository(UserRepository):

    def __init__(self, db_path: str):
        self._db_path = db_path

    async def ensure_schema(self) -> None:
        """Create the users table if it doesn't exist yet. Call this once at
        startup — not per-request."""
        await self._run(self._ensure_schema_sync)

    async def find_by_username(self, username: str) -> UserRecord | None:
        return await self._run(self._find_by_username_sync, username)

    async def create_user(self, username: str, password_hash: str, salt: str) -> UserRecord:
        return await self._run(self._create_user_sync, username, password_hash, salt)

    async def update_rating(self, username: str, new_rating: int) -> None:
        await self._run(self._update_rating_sync, username, new_rating)

    async def _run(self, func, *args):
        # get_running_loop() (not stored at construction time) since this
        # repository may be constructed before the event loop is running.
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, functools.partial(func, *args))

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)

    def _ensure_schema_sync(self) -> None:
        with open(_SCHEMA_PATH, "r", encoding="utf-8") as f:
            schema_sql = f.read()
        conn = self._connect()
        try:
            conn.executescript(schema_sql)
            conn.commit()
        finally:
            conn.close()

    def _find_by_username_sync(self, username: str) -> UserRecord | None:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT username, password_hash, salt, rating FROM users WHERE username = ?",
                (username,),
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            return None
        return UserRecord(username=row[0], password_hash=row[1], salt=row[2], rating=row[3])

    def _create_user_sync(self, username: str, password_hash: str, salt: str) -> UserRecord:
        created_at = datetime.now(timezone.utc).isoformat()
        conn = self._connect()
        try:
            # A PRIMARY KEY violation raises sqlite3.IntegrityError here,
            # which propagates out of run_in_executor unchanged — the caller
            # (AuthService) is expected to check existence first via
            # find_by_username and translate that into an "already taken"
            # response; this method doesn't swallow the DB error itself.
            conn.execute(
                "INSERT INTO users (username, password_hash, salt, rating, created_at) "
                "VALUES (?, ?, ?, 1200, ?)",
                (username, password_hash, salt, created_at),
            )
            conn.commit()
        finally:
            conn.close()
        return UserRecord(username=username, password_hash=password_hash, salt=salt, rating=1200)

    def _update_rating_sync(self, username: str, new_rating: int) -> None:
        conn = self._connect()
        try:
            conn.execute(
                "UPDATE users SET rating = ? WHERE username = ?",
                (new_rating, username),
            )
            conn.commit()
        finally:
            conn.close()
