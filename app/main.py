import asyncio
import json
import os
import re
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from redis.asyncio import Redis

from app import database


BASE_DIR = Path(__file__).resolve().parent.parent
PUBLIC_DIR = BASE_DIR / "public"
USERNAME_RE = re.compile(r"[^\x00-\x1f]{1,20}")
MAX_MESSAGE_LENGTH = 500
PRESENCE_TTL_SECONDS = 45
redis_client: Redis | None = None


def get_redis() -> Redis:
    global redis_client
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        raise RuntimeError("REDIS_URL is not configured")
    if redis_client is None:
        redis_client = Redis.from_url(redis_url, decode_responses=True)
    return redis_client


async def online_users(redis: Redis, room: str) -> list[str]:
    key = f"chat:presence:{room}"
    await redis.zremrangebyscore(key, "-inf", time.time() - PRESENCE_TTL_SECONDS)
    members = await redis.zrange(key, 0, -1)
    return sorted((member.split(":", 1)[1] for member in members if ":" in member), key=str.casefold)


async def publish(redis: Redis, room: str, event: dict) -> None:
    await redis.publish(f"chat:events:{room}", json.dumps(event))


app = FastAPI(title="The Hive Realtime Chat")
app.mount("/static", StaticFiles(directory=PUBLIC_DIR / "static"), name="static")


@app.get("/")
async def index():
    return FileResponse(PUBLIC_DIR / "index.html")


@app.get("/rooms")
async def rooms():
    try:
        return {"rooms": await database.get_rooms()}
    except Exception as error:
        raise HTTPException(status_code=503, detail="Chat storage is unavailable") from error


@app.get("/health")
async def health():
    return {"status": "ok", "storageConfigured": bool(os.getenv("SUPABASE_URL") and
            (os.getenv("SUPABASE_SECRET_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY"))),
            "redisConfigured": bool(os.getenv("REDIS_URL"))}


@app.websocket("/ws")
async def websocket_chat(socket: WebSocket):
    await socket.accept()
    redis = None
    pubsub = None
    listener = None
    room = username = member = None
    connection_id = uuid.uuid4().hex
    send_lock = asyncio.Lock()

    async def send(payload: dict):
        async with send_lock:
            await socket.send_json(payload)

    try:
        try:
            first = json.loads(await socket.receive_text())
        except (json.JSONDecodeError, WebSocketDisconnect):
            await send({"type": "error", "message": "Invalid join request"})
            return
        if not isinstance(first, dict) or first.get("type") != "join_room":
            await send({"type": "error", "message": "Join a room first"})
            return

        raw_username = first.get("username")
        requested_room = first.get("room")
        username = raw_username.strip() if isinstance(raw_username, str) else ""
        if not USERNAME_RE.fullmatch(username):
            await send({"type": "error", "message": "Username must be 1–20 characters"})
            return
        try:
            room_names = await database.get_rooms()
        except Exception:
            await send({"type": "error", "message": "Chat storage is unavailable"})
            return
        if not isinstance(requested_room, str) or requested_room not in room_names:
            await send({"type": "error", "message": "Unknown room"})
            return
        room = requested_room
        try:
            redis = get_redis()
            pubsub = redis.pubsub()
            await pubsub.subscribe(f"chat:events:{room}")
            presence_key = f"chat:presence:{room}"
            await redis.zremrangebyscore(presence_key, "-inf", time.time() - PRESENCE_TTL_SECONDS)
            members = await redis.zrange(presence_key, 0, -1)
            if any(entry.partition(":")[2].casefold() == username.casefold() for entry in members):
                await send({"type": "error", "message": "Username already used in this room"})
                return
            member = f"{connection_id}:{username}"
            await redis.zadd(presence_key, {member: time.time()})
            await redis.expire(presence_key, PRESENCE_TTL_SECONDS * 2)
            history = await database.get_history(room)
        except Exception:
            await send({"type": "error", "message": "Realtime or chat storage is unavailable"})
            return

        await send({"type": "history", "room": room, "messages": history})
        await publish(redis, room, {"type": "presence_update", "room": room,
                                     "users": await online_users(redis, room)})

        async def relay_room_events():
            async for event in pubsub.listen():
                if event.get("type") != "message":
                    continue
                try:
                    payload = json.loads(event["data"])
                    if payload.get("sender_id") != connection_id:
                        await send(payload)
                except (json.JSONDecodeError, RuntimeError, WebSocketDisconnect):
                    return

        listener = asyncio.create_task(relay_room_events())
        while True:
            try:
                raw = await asyncio.wait_for(socket.receive_text(), timeout=20)
            except asyncio.TimeoutError:
                await redis.zadd(presence_key, {member: time.time()})
                await redis.expire(presence_key, PRESENCE_TTL_SECONDS * 2)
                await send({"type": "ping"})
                continue
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                await send({"type": "error", "message": "Invalid JSON"})
                continue
            if not isinstance(event, dict):
                await send({"type": "error", "message": "Invalid message"})
                continue
            if event.get("type") == "pong":
                continue
            await redis.zadd(presence_key, {member: time.time()})
            await redis.expire(presence_key, PRESENCE_TTL_SECONDS * 2)
            if event.get("type") == "send_message":
                text = event.get("text")
                if not isinstance(text, str) or not text.strip():
                    await send({"type": "error", "message": "Message cannot be empty"})
                    continue
                if len(text.strip()) > MAX_MESSAGE_LENGTH:
                    await send({"type": "error", "message": "Message cannot exceed 500 characters"})
                    continue
                try:
                    message = await database.add_message(room, username, text.strip())
                    await publish(redis, room, {"type": "message", **message,
                                                "sender_id": connection_id})
                except Exception:
                    await send({"type": "error", "message": "Message could not be saved"})
            elif event.get("type") == "typing":
                is_typing = event.get("is_typing")
                if isinstance(is_typing, bool):
                    await publish(redis, room, {"type": "typing", "username": username,
                                                "is_typing": is_typing, "sender_id": connection_id})
            else:
                await send({"type": "error", "message": "Unknown message type"})
    except WebSocketDisconnect:
        pass
    except Exception:
        try:
            await send({"type": "error", "message": "Chat connection failed"})
        except Exception:
            pass
    finally:
        if listener:
            listener.cancel()
            try:
                await listener
            except asyncio.CancelledError:
                pass
        if pubsub:
            await pubsub.aclose()
        if redis and room and member:
            await redis.zrem(f"chat:presence:{room}", member)
            await publish(redis, room, {"type": "typing", "username": username,
                                        "is_typing": False, "sender_id": connection_id})
            await publish(redis, room, {"type": "presence_update", "room": room,
                                        "users": await online_users(redis, room)})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
