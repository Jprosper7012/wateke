

# Realtime Chat (WebSockets MVP)

A small chat app where messages appear instantly for everyone in the room, with no page refresh.

**Features**

- **Rooms**: separate chat spaces (`general`, `football`, `music`)
- **Online presence**: a live list of who is in the room
- **Typing indicators**: "Ada is typing..."
- **Message history**: the last 50 messages are saved and shown when you join

**Tech stack**: Python + FastAPI (WebSockets), SQLite (storage), plain HTML/CSS/JavaScript (UI).

**Live demo:** 

---

## How it works

```
 Browser A ──┐                          ┌── SQLite file (messages, rooms)
             ├── WebSocket ──> Server ──┤
 Browser B ──┘   (always open)          └── In-memory dictionary (who is online)
```

1. A browser opens one WebSocket connection to the server and **keeps it open**.
2. The browser sends small JSON messages. The server sends JSON messages back.
3. The server remembers who is online in a dictionary: `{ "general": { "Ada": <connection> } }`.
4. Chat messages are saved to SQLite so history survives restarts.

---

To Run it on your computer

You need **Python 3.10 or newer**.


## Environment variables

| Variable  | Default   | What it does |
|-----------|-----------|--------------|
| `DB_PATH` | `chat.db` | Where the SQLite database file is stored |
| `PORT`    | `8000`    | Port the server listens on (set by the hosting platform when deployed) |

Both are optional. See `.env.example`.

---

## Message protocol (the "language" client and server speak)

**Client → Server**

| `type`         | Extra fields             | Meaning |
|----------------|--------------------------|---------|
| `join_room`    | `username`, `room`       | "I want to enter this room" (must be the first message) |
| `send_message` | `text`                   | "Send this to the room" |
| `typing`       | `is_typing` (true/false) | "I started / stopped typing" |

**Server → Client**

| `type`            | Fields                                  | Meaning |
|-------------------|-----------------------------------------|---------|
| `history`         | `room`, `messages[]`                    | Old messages, sent once after joining |
| `message`         | `id`, `room`, `username`, `text`, `created_at` | A new message |
| `presence_update` | `room`, `users[]`                       | Who is online now |
| `typing`          | `username`, `is_typing`                 | Someone started / stopped typing |
| `error`           | `message`                               | Something was rejected (explains why) |

## HTTP endpoints

| Method | Path       | Purpose |
|--------|------------|---------|
| GET    | `/`        | The chat page |
| GET    | `/rooms`   | List of rooms |
| GET    | `/health`  | Health check + how many users are online per room |
| WS     | `/ws`      | The WebSocket connection |

## Data model

```sql
rooms (
  id    INTEGER PRIMARY KEY AUTOINCREMENT,
  name  TEXT UNIQUE NOT NULL
)

messages (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  room_id     INTEGER NOT NULL REFERENCES rooms(id),
  username    TEXT NOT NULL,
  text        TEXT NOT NULL,
  created_at  TEXT NOT NULL      -- UTC timestamp
)
```

Tables are created automatically on startup. Presence and typing are **not** stored; they only exist while people are connected.

---

## Validation and error handling

| Situation | What happens |
|-----------|--------------|
| Empty or whitespace-only message | Rejected with an error, not broadcast |
| Message longer than 500 characters | Rejected with an error |
| Username empty or longer than 20 characters | Rejected |
| Room does not exist | Rejected |
| Username already used in that room | Rejected |
| Sending a message before joining | Rejected ("Join a room first") |
| Invalid JSON / unknown message type | Rejected |
| User closes the tab or loses connection | Removed from the online list, others are notified |
| Someone tries to inject HTML in a message | Shown as plain text (the page uses `textContent`) |

---

## Tests

```bash
pytest -v
```

**Test strategy**

- **Happy path**: two users join the same room, one sends a message, both receive it.
- **Major failure path**: an empty message is rejected with an error and is *not* sent to anyone.
- **Extra checks**: unknown room, duplicate username, too-long message, sending before joining, bad JSON, history saved and shown to new users, rooms stay separate, typing events reach others only, presence updates when someone leaves.

Each test uses its own temporary database, so tests never affect each other or real data.

---
