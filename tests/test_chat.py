from fastapi.testclient import TestClient

from app.main import app


def test_message_broadcast_and_history(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "chat.sqlite3"))
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ada, client.websocket_connect("/ws") as lin:
            ada.send_json({"type": "join_room", "username": "Ada", "room": "general"})
            assert ada.receive_json()["type"] == "history"
            assert ada.receive_json()["type"] == "presence_update"
            lin.send_json({"type": "join_room", "username": "Lin", "room": "general"})
            assert lin.receive_json()["type"] == "history"
            assert lin.receive_json()["type"] == "presence_update"
            assert ada.receive_json()["users"] == ["Ada", "Lin"]
            ada.send_json({"type": "send_message", "text": "Hello, room!"})
            ada_message = ada.receive_json()
            lin_message = lin.receive_json()
            assert ada_message == lin_message
            assert (ada_message["username"], ada_message["text"]) == ("Ada", "Hello, room!")

        with client.websocket_connect("/ws") as newcomer:
            newcomer.send_json({"type": "join_room", "username": "Sam", "room": "general"})
            history = newcomer.receive_json()
            assert history["messages"][-1]["text"] == "Hello, room!"


def test_empty_message_is_rejected_and_not_broadcast(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "chat.sqlite3"))
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as sender, client.websocket_connect("/ws") as listener:
            sender.send_json({"type": "join_room", "username": "Ada", "room": "general"})
            sender.receive_json()
            sender.receive_json()
            listener.send_json({"type": "join_room", "username": "Lin", "room": "general"})
            listener.receive_json()
            listener.receive_json()
            sender.receive_json()
            sender.send_json({"type": "send_message", "text": "   "})
            assert sender.receive_json() == {"type": "error", "message": "Message cannot be empty"}
            assert client.get("/health").json()["online"]["general"] == 2


def test_validation_and_rooms_endpoint(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "chat.sqlite3"))
    with TestClient(app) as client:
        assert client.get("/rooms").json()["rooms"] == ["general", "football", "music"]
        with client.websocket_connect("/ws") as socket:
            socket.send_text("not json")
            assert socket.receive_json()["message"] == "Invalid JSON"
        with client.websocket_connect("/ws") as socket:
            socket.send_json({"type": "join_room", "username": "Ada", "room": "nope"})
            assert socket.receive_json()["message"] == "Unknown room"


def test_typing_presence_and_duplicate_names(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "chat.sqlite3"))
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ada, client.websocket_connect("/ws") as lin:
            ada.send_json({"type": "join_room", "username": "Ada", "room": "music"})
            ada.receive_json()
            ada.receive_json()
            lin.send_json({"type": "join_room", "username": "Lin", "room": "music"})
            lin.receive_json()
            lin.receive_json()
            ada.receive_json()
            ada.send_json({"type": "typing", "is_typing": True})
            assert lin.receive_json() == {"type": "typing", "username": "Ada", "is_typing": True}
            with client.websocket_connect("/ws") as duplicate:
                duplicate.send_json({"type": "join_room", "username": "ada", "room": "music"})
                assert "already used" in duplicate.receive_json()["message"]

