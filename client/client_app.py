"""client/client_app.py

KungFu Chess – remote graphical entry point. Mirrors main_gui.py exactly,
except the engine passed into App is a RemoteGameEngine (backed by a
ServerGateway) instead of a local GameEngine — App itself is unmodified.

Run from any directory:
    python -m client.client_app
"""
import logging
import os
import sys

# Insert the project root (two levels up: client/ -> repo root) at the front
# of sys.path so all package imports work regardless of working directory.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from config import settings
from gui.asset_loader import Assets
from gui.app import App
from infrastructure.bus.in_memory_bus import InMemoryEventBus
from client.server_gateway import ServerGateway
from client.remote_engine import RemoteGameEngine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("kungfu_chess.client")


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
        engine = RemoteGameEngine(gateway, bus)
        App(engine, assets, config=settings).run()
    finally:
        gateway.close()


if __name__ == "__main__":
    main()
