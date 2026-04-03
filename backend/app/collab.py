from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from dataclasses import dataclass

from fastapi import WebSocket


@dataclass
class Client:
    websocket: WebSocket
    client_id: str


class CollaborationHub:
    def __init__(self) -> None:
        self.rooms: dict[int, list[Client]] = defaultdict(list)
        self.lock = asyncio.Lock()

    async def connect(self, doc_id: int, websocket: WebSocket, client_id: str) -> None:
        await websocket.accept()
        async with self.lock:
            self.rooms[doc_id].append(Client(websocket=websocket, client_id=client_id))

    async def disconnect(self, doc_id: int, websocket: WebSocket) -> int:
        async with self.lock:
            clients = self.rooms.get(doc_id, [])
            self.rooms[doc_id] = [c for c in clients if c.websocket is not websocket]
            count = len(self.rooms[doc_id])
            if count == 0:
                self.rooms.pop(doc_id, None)
            return count

    async def broadcast(self, doc_id: int, message: dict, sender: WebSocket | None = None) -> None:
        encoded = json.dumps(message)
        stale: list[WebSocket] = []
        async with self.lock:
            recipients = list(self.rooms.get(doc_id, []))

        for client in recipients:
            if sender is not None and client.websocket is sender:
                continue
            try:
                await client.websocket.send_text(encoded)
            except Exception:
                stale.append(client.websocket)

        if stale:
            async with self.lock:
                current = self.rooms.get(doc_id, [])
                self.rooms[doc_id] = [c for c in current if c.websocket not in stale]

    async def room_size(self, doc_id: int) -> int:
        async with self.lock:
            return len(self.rooms.get(doc_id, []))
