"""client/client_app.py

KungFu Chess – remote graphical entry point. Mirrors main_gui.py exactly,
except the engine passed into App is a RemoteGameEngine (backed by a
ServerGateway) instead of a local GameEngine — App itself is unmodified.

Run from any directory:
    python -m client.client_app
"""
from __future__ import annotations

import getpass
import logging
import os
import sys
import time

# Insert the project root (two levels up: client/ -> repo root) at the front
# of sys.path so all package imports work regardless of working directory.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from config import settings
from gui.asset_loader import Assets
from gui.app import App
from infrastructure.bus.in_memory_bus import InMemoryEventBus
from protocol.messages import ErrorMessage, GameStateEvent
from client.server_gateway import SERVER_EVENTS_TOPIC, ServerGateway
from client.remote_engine import RemoteGameEngine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("kungfu_chess.client")

_AUTH_RESPONSE_TIMEOUT_S = 5.0
_AUTH_POLL_INTERVAL_S = 0.02


def _prompt_login_or_register() -> str:
    while True:
        choice = input("1. Login  2. Register — choose: ").strip()
        if choice in ("1", "2"):
            return choice
        print("Please enter 1 or 2.")


def _prompt_for_username() -> str:
    while True:
        username = input("Enter your username: ").strip()
        if username:
            return username
        print("Username cannot be empty — please try again.")


def _prompt_for_password() -> str:
    return getpass.getpass("Enter your password: ")


def _await_auth_response(bus: InMemoryEventBus) -> object | None:
    """Poll the bus for the server's reply to a Register/LoginCommand: a
    GameStateEvent means authentication succeeded (the handshake completed
    and the session's ticks are now flowing to this connection); an
    ErrorMessage means it failed. Returns None on timeout.

    Same lightweight polling style as RemoteGameEngine's initial-state wait
    — a short-lived subscription plus a bounded time.sleep loop — reused
    here rather than inventing a new synchronization mechanism.
    """
    received: list = []
    subscription = bus.subscribe(SERVER_EVENTS_TOPIC, received.append)
    try:
        deadline = time.monotonic() + _AUTH_RESPONSE_TIMEOUT_S
        while not received:
            if time.monotonic() >= deadline:
                return None
            time.sleep(_AUTH_POLL_INTERVAL_S)
        return received[0]
    finally:
        subscription.unsubscribe()


def _authenticate(gateway: ServerGateway, bus: InMemoryEventBus) -> str:
    """Prompt for login/register credentials and keep retrying until the
    server confirms success (a GameStateEvent), printing any ErrorMessage
    and re-prompting on failure or timeout."""
    while True:
        choice = _prompt_login_or_register()
        username = _prompt_for_username()
        password = _prompt_for_password()

        if choice == "1":
            gateway.send_credentials_login(username, password)
        else:
            gateway.send_register(username, password)

        response = _await_auth_response(bus)

        if response is None:
            print("No response from the server — please try again.")
            continue
        if isinstance(response, ErrorMessage):
            print(f"Authentication failed: {response.message}")
            continue
        if isinstance(response, GameStateEvent):
            return username

        print("Unexpected response from the server — please try again.")


def main():
    assets = Assets(cell_px=settings.CELL_SIZE)
    bus = InMemoryEventBus()
    gateway = ServerGateway(settings.WS_HOST, settings.WS_PORT, bus, logger)

    try:
        gateway.connect()
    except ConnectionError as exc:
        print(f"Could not connect to the KungFu Chess server: {exc}")
        return

    try:
        _authenticate(gateway, bus)
        engine = RemoteGameEngine(gateway, bus)
        App(engine, assets, config=settings).run()
    finally:
        gateway.close()


if __name__ == "__main__":
    main()
