import asyncio
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app import database
from app import main
from app.main import app


class FakePubSub:
    def __init__(self, redis):
        self.redis = redis
        self.queue = asyncio.Queue()
        self.channels = set()

    async def subscribe(self, channel):
        self.channels.add(channel)
        self.redis.subscribers.setdefault(channel, set()).add(self)

    async def listen(self):
        while True:
            event = await self.queue.get()
            if event is None:
                return
            yield event

    async def aclose(self):
        for channel in self.channels:
            self.redis.subscribers.get(channel, set()).discard(self)
        self.queue.put_nowait(None)


class FakeRedis:
    def __init__(self):
        self.sorted_sets = {}
        self.subscribers = {}

    def pubsub(self):
        return FakePubSub(self)

    async def publish(self, channel, data):
        for subscriber in list(self.subscribers.get(channel, set())):
            subscriber.queue.put_nowait({"type": "message", "data": data})

    async def zremrangebyscore(self, key, minimum, maximum):
        entries = self.sorted_sets.setdefault(key, {})
        cutoff = float(maximum)
        for member, score in list(entries.items()):
            if score <= cutoff:
                del entries[member]

    async def zrange(self, key, start, end):
        entries = self.sorted_sets.setdefault(key, {})
        members = [member for member, _ in sorted(entries.items(), key=lambda row: row[1])]
        return members[start:] if end == -1 else members[start:end + 1]

    async def zadd(self, key, entries):
        self.sorted_sets.setdefault(key, {}).update(entries)

    async def expire(self, key, seconds):
        return True

    async def zrem(self, key, member):
        self.sorted_sets.setdefault(key, {}).pop(member, None)


def configure_test_services(monkeypatch):
    redis = FakeRedis()
    messages = []

    async def get_rooms():
        return ["general", "football", "music"]

    async def get_history(room, limit=50):
        return [message for message in messages if message["room"] == room][-limit:]

    async def add_message(room, username, text):
        message = {"id": len(messages) + 1, "room": room, "username": username,
                   "text": text, "created_at": datetime.now(timezone.utc).isoformat()}
        messages.append(message)
        return message

    monkeypatch.setattr(main, "get_redis", lambda: redis)
    monkeypatch.setattr(database, "get_rooms", get_rooms)
    monkeypatch.setattr(database, "get_history", get_history)
    monkeypatch.setattr(database, "add_message", add_message)


def test_two_clients_exchange_message_and_load_history(monkeypatch):
    configure_test_services(monkeypatch)
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ada, client.websocket_connect("/ws") as lin:
            ada.send_json({"type": "join_room", "username": "Ada", "room": "general"})
            assert ada.receive_json()["type"] == "history"
            assert ada.receive_json()["type"] == "presence_update"
            lin.send_json({"type": "join_room", "username": "Lin", "room": "general"})
            assert lin.receive_json()["type"] == "history"
            assert lin.receive_json()["users"] == ["Ada", "Lin"]
            assert ada.receive_json()["users"] == ["Ada", "Lin"]
            ada.send_json({"type": "send_message", "text": "Hello, room!"})
            event = lin.receive_json()
            assert event["type"] == "message"
            assert (event["username"], event["text"]) == ("Ada", "Hello, room!")

        with client.websocket_connect("/ws") as newcomer:
            newcomer.send_json({"type": "join_room", "username": "Sam", "room": "general"})
            history = newcomer.receive_json()
            assert history["messages"][-1]["text"] == "Hello, room!"


def test_empty_message_gets_error_without_broadcast(monkeypatch):
    configure_test_services(monkeypatch)
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as sender, client.websocket_connect("/ws") as listener:
            sender.send_json({"type": "join_room", "username": "Ada", "room": "general"})
            sender.receive_json()
            sender.receive_json()
            listener.send_json({"type": "join_room", "username": "Lin", "room": "general"})
            listener.receive_json()
            listener.receive_json()
            sender.receive_json()
            sender.send_json({"type": "send_message", "text": "  "})
            assert sender.receive_json() == {"type": "error", "message": "Message cannot be empty"}
            listener.send_json({"type": "send_message", "text": "still connected"})
            assert sender.receive_json()["text"] == "still connected"


def test_room_and_join_validation(monkeypatch):
    configure_test_services(monkeypatch)
    with TestClient(app) as client:
        assert client.get("/rooms").json()["rooms"] == ["general", "football", "music"]
        with client.websocket_connect("/ws") as socket:
            socket.send_json({"type": "join_room", "username": "Ada", "room": "missing"})
            assert socket.receive_json()["message"] == "Unknown room"
