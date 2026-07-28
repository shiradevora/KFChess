"""application/auth_service.py

AuthService — hashes/verifies passwords and coordinates with a
UserRepository to implement registration and login. All password-hashing
and credential-comparison logic lives here; the wire protocol
(RegisterCommand/LoginCommand) and connection lifecycle
(server/connection_handler.py) know nothing about hashing or storage.
"""
from __future__ import annotations

import hashlib
import hmac
import os
from dataclasses import dataclass

from ports.user_repository import UserRepository

_HASH_NAME = "sha256"
_PBKDF2_ITERATIONS = 200_000
_SALT_BYTES = 16


@dataclass(frozen=True)
class AuthResult:
    success: bool
    error: str | None = None


def _hash_password(password: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac(
        _HASH_NAME, password.encode("utf-8"), salt, _PBKDF2_ITERATIONS
    ).hex()


class AuthService:

    def __init__(self, user_repository: UserRepository):
        self._user_repository = user_repository

    async def register(self, username: str, password: str) -> AuthResult:
        if not username:
            return AuthResult(success=False, error="Username cannot be empty")

        existing = await self._user_repository.find_by_username(username)
        if existing is not None:
            # Deliberate, accepted trade-off: unlike login() (which always
            # returns one generic failure to avoid username enumeration),
            # registration failure DOES reveal that the username is taken.
            # Fully hiding this would hurt registration UX (users need to
            # know to pick a different name) for negligible security benefit
            # in this project's threat model.
            return AuthResult(success=False, error="Username already taken")

        salt = os.urandom(_SALT_BYTES)
        password_hash = _hash_password(password, salt)
        await self._user_repository.create_user(
            username=username, password_hash=password_hash, salt=salt.hex(),
        )
        return AuthResult(success=True)

    async def login(self, username: str, password: str) -> AuthResult:
        user = await self._user_repository.find_by_username(username)

        if user is not None:
            computed_hash = _hash_password(password, bytes.fromhex(user.salt))
            credentials_valid = hmac.compare_digest(computed_hash, user.password_hash)
        else:
            credentials_valid = False

        # Single unified check feeding one return: "unknown username" and
        # "wrong password" must be indistinguishable to the caller (this is
        # the username-enumeration mitigation) — computing one boolean and
        # branching once, instead of returning the same literal string from
        # two separate ifs, means the two cases can't accidentally diverge
        # later.
        if not credentials_valid:
            return AuthResult(success=False, error="Invalid username or password")

        return AuthResult(success=True)
