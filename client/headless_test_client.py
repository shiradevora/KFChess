"""client/headless_test_client.py

Throwaway manual test script for eyeballing the server end-to-end: connects,
sends one ClickCommand, prints the next few messages it receives, then exits.
Not covered by pytest, not production code.

GameStateEvent decoding isn't implemented in protocol/codec.py yet (that's
scoped for a later step), so anything other than ClickCommand/JumpCommand/
ErrorMessage is printed as raw JSON.
"""
import asyncio

import websockets

from config import settings
from protocol.codec import DecodeError, decode, encode
from protocol.messages import ClickCommand

_MESSAGES_TO_PRINT = 5


async def main() -> None:
    uri = f"ws://{settings.WS_HOST}:{settings.WS_PORT}"
    async with websockets.connect(uri) as ws:
        click = ClickCommand(x=350, y=650)
        await ws.send(encode(click))
        print(f"sent: {click}")

        for _ in range(_MESSAGES_TO_PRINT):
            try:
                raw = await ws.recv()
            except websockets.exceptions.ConnectionClosed:
                print("connection closed by server")
                break

            try:
                print("received:", decode(raw))
            except DecodeError:
                print("received (raw JSON):", raw)


if __name__ == "__main__":
    asyncio.run(main())
