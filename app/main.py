import asyncio
import json
import os
import re
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import database


BASE_DIR = Path(__file__).resolve().parent
USERNAME_RE = re.compile(r"[^\x00-\x1f]{1,20}")
MAX_MESSAGE_LENGTH = 500


class ChatHub:
    def __init__(self):
        self.rooms: dict[str, dict[WebSocket, str]] = defaultdict(dict)
        self.lock = asyncio.Lock()

    async def join(self, room: str, username: str, socket: WebSocket) -> bool:
        async with self.lock:
            if any(name.casefold() == username.casefold()
                   for name in self.rooms[room].values()):
                return False
            self.rooms[room][socket] = username
        return True

    async def leave(self, socket: WebSocket) -> tuple[str, str] | None:
        async with self.lock:
            for room, members in list(self.rooms.items()):
                if socket in members:
                    username = members.pop(socket)
                    if not members:
                        self.rooms.pop(room, None)
                    return room, username
        return None

    async def broadcast(self, room: str, payload: dict, exclude: WebSocket | None = None):
        async with self.lock:
            recipients = [socket for socket in self.rooms.get(room, {}) if socket != exclude]
        if recipients:
            await asyncio.gather(*(self._send(socket, payload) for socket in recipients))

    async def _send(self, socket: WebSocket, payload: dict):
        try:
            await socket.send_json(payload)
        except (RuntimeError, WebSocketDisconnect):
            pass

    async def presence(self, room: str) -> list[str]:
        async with self.lock:
            return sorted(self.rooms.get(room, {}).values(), key=str.casefold)


hub = ChatHub()


@asynccontextmanager
async def lifespan(_: FastAPI):
    database.initialize()
    yield


app = FastAPI(title="Realtime Chat", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


@app.get("/")
async def index():
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.get("/rooms")
async def rooms():
    return {"rooms": database.get_rooms()}


@app.get("/health")
async def health():
    async with hub.lock:
        online = {room: len(members) for room, members in hub.rooms.items()}
    return {"status": "ok", "online": online}


@app.websocket("/ws")
async def websocket_chat(socket: WebSocket):
    await socket.accept()
    room = username = None
    try:
        first = await socket.receive_text()
        try:
            request = json.loads(first)
        except json.JSONDecodeError:
            await socket.send_json({"type": "error", "message": "Invalid JSON"})
            return
        if not isinstance(request, dict) or request.get("type") != "join_room":
            await socket.send_json({"type": "error", "message": "Join a room first"})
            return

        raw_username = request.get("username")
        requested_room = request.get("room")
        if not isinstance(raw_username, str):
            await socket.send_json({"type": "error", "message": "Username must be 1–20 characters"})
            return
        username = raw_username.strip()
        if not USERNAME_RE.fullmatch(username):
            await socket.send_json({"type": "error", "message": "Username must be 1–20 characters"})
            return
        if not isinstance(requested_room, str) or requested_room not in database.get_rooms():
            await socket.send_json({"type": "error", "message": "Unknown room"})
            return
        room = requested_room
        if not await hub.join(room, username, socket):
            await socket.send_json({"type": "error", "message": "Username already used in this room"})
            return

        await socket.send_json({"type": "history", "room": room,
                                "messages": database.get_history(room)})
        await hub.broadcast(room, {"type": "presence_update", "room": room,
                                   "users": await hub.presence(room)})

        while True:
            raw = await socket.receive_text()
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                await socket.send_json({"type": "error", "message": "Invalid JSON"})
                continue
            if not isinstance(event, dict):
                await socket.send_json({"type": "error", "message": "Invalid message"})
                continue
            kind = event.get("type")
            if kind == "send_message":
                text = event.get("text")
                if not isinstance(text, str) or not text.strip():
                    await socket.send_json({"type": "error", "message": "Message cannot be empty"})
                    continue
                if len(text.strip()) > MAX_MESSAGE_LENGTH:
                    await socket.send_json({"type": "error", "message": "Message cannot exceed 500 characters"})
                    continue
                message = database.add_message(room, username, text.strip())
                await hub.broadcast(room, {"type": "message", **message})
            elif kind == "typing":
                is_typing = event.get("is_typing")
                if isinstance(is_typing, bool):
                    await hub.broadcast(room, {"type": "typing", "username": username,
                                               "is_typing": is_typing}, exclude=socket)
            else:
                await socket.send_json({"type": "error", "message": "Unknown message type"})
    except WebSocketDisconnect:
        pass
    finally:
        if room is not None and username is not None:
            departed = await hub.leave(socket)
            if departed:
                await hub.broadcast(room, {"type": "typing", "username": username,
                                           "is_typing": False})
                await hub.broadcast(room, {"type": "presence_update", "room": room,
                                           "users": await hub.presence(room)})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
