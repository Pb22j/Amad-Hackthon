"""PersonaPlex realtime WebSocket bridge.

PersonaPlex is used as a full-duplex English voice surface. Its documented
server protocol sends and receives binary frames with a one-byte type prefix:
0x00 handshake, 0x01 Opus audio, and 0x02 UTF-8 text token.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from urllib.parse import urlencode

import websockets
from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect


@dataclass(frozen=True)
class PersonaPlexBridgeConfig:
    base_url: str
    api_key: str
    voice_prompt: str
    text_prompt: str

    def websocket_url(self) -> str:
        base = self.base_url.rstrip("/")
        if base.startswith("http://"):
            base = "ws://" + base.removeprefix("http://")
        elif base.startswith("https://"):
            base = "wss://" + base.removeprefix("https://")
        query = urlencode(
            {
                "api_key": self.api_key,
                "voice_prompt": self.voice_prompt,
                "text_prompt": self.text_prompt,
            }
        )
        return f"{base}/api/chat?{query}"


class PersonaPlexBridgeError(RuntimeError):
    """Raised when the PersonaPlex bridge cannot run."""


async def bridge_personaplex_websocket(client_ws: WebSocket, config: PersonaPlexBridgeConfig) -> None:
    if not config.api_key:
        raise PersonaPlexBridgeError("PERSONAPLEX_API_KEY is missing")

    await client_ws.accept()
    persona_url = config.websocket_url()
    async with websockets.connect(persona_url) as persona_ws:
        await client_ws.send_json({"type": "personaplex_connected"})
        client_to_persona = asyncio.create_task(_forward_client_to_persona(client_ws, persona_ws))
        persona_to_client = asyncio.create_task(_forward_persona_to_client(persona_ws, client_ws))
        done, pending = await asyncio.wait(
            {client_to_persona, persona_to_client},
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
        for task in done:
            task.result()


async def _forward_client_to_persona(client_ws: WebSocket, persona_ws: websockets.WebSocketClientProtocol) -> None:
    try:
        while True:
            message = await client_ws.receive()
            if "bytes" in message and message["bytes"] is not None:
                audio = message["bytes"]
                if not audio.startswith(b"\x01"):
                    audio = b"\x01" + audio
                await persona_ws.send(audio)
            elif "text" in message and message["text"] is not None:
                if message["text"] == '{"type":"close"}':
                    await persona_ws.close()
                    return
    except WebSocketDisconnect:
        await persona_ws.close()


async def _forward_persona_to_client(persona_ws: websockets.WebSocketClientProtocol, client_ws: WebSocket) -> None:
    async for message in persona_ws:
        if isinstance(message, bytes):
            if message.startswith(b"\x00"):
                await client_ws.send_json({"type": "personaplex_handshake"})
            elif message.startswith(b"\x01"):
                await client_ws.send_bytes(message[1:])
            elif message.startswith(b"\x02"):
                await client_ws.send_json(
                    {
                        "type": "personaplex_text",
                        "text": message[1:].decode("utf-8", errors="replace"),
                    }
                )
            else:
                await client_ws.send_bytes(message)
        else:
            await client_ws.send_text(message)

