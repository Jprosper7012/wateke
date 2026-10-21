# The Hive — Realtime Chat

A small room-based chat app with live messages, online presence, typing indicators, and persistent message history. The project is split into five practical areas: WebSocket routing (`app/main.py`), persistence (`app/database.py`), presence and typing (`ChatHub`), browser UI (`app/static`), and tests/deployment/demo materials.

## Run locally

Requires Python 3.10 or newer.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open http://localhost:8000. Choose a name and one of the seeded rooms: `general`, `football`, or `music`.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `DB_PATH` | `chat.db` | SQLite database location |
| `PORT` | `8000` | Listening port for `python -m app.main` and the Render start command |

See `.env.example`. SQLite persists history when the configured file is on durable storage. On hosts with ephemeral disks, provision a persistent disk and set `DB_PATH` to its mount path.

## Architecture and data

- FastAPI serves the page, room list, health check, and `/ws` WebSocket endpoint.
- SQLite stores seeded rooms and messages; the newest 50 messages are sent when a user joins.
- An in-process hub tracks each room's connected sockets. Presence and typing are transient and reset when the service restarts.
- Messages are validated and saved before being broadcast. The browser uses `textContent` when rendering user content.

```text
Browser ── WebSocket /ws ── FastAPI ── SQLite
                             └── room membership and typing state
```

### Message protocol

The first client event must be `{"type":"join_room","username":"Ada","room":"general"}`. After joining, clients send `send_message` with `text`, or `typing` with a boolean `is_typing`.

Server events are `history` (`room`, `messages`), `message` (`id`, `room`, `username`, `text`, `created_at`), `presence_update` (`room`, `users`), `typing` (`username`, `is_typing`), and `error` (`message`).

### HTTP endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/` | Chat UI |
| GET | `/rooms` | Available rooms |
| GET | `/health` | Health status and online counts |
| WS | `/ws` | Chat connection |

## Tests

```bash
pytest -v
```

The suite checks a two-person conversation and persisted history, rejection of empty messages, room and JSON validation, typing broadcasts, and duplicate names. Each test uses an isolated temporary database.

## Deploy to Render

This repository includes `render.yaml`. Create a Render web service from the repository and attach a persistent disk at `/var/data`; set `DB_PATH=/var/data/chat.db` in the service environment (the blueprint configures this). The service listens on Render's `PORT` and serves both UI and WebSockets from one origin. Use `/health` for the health check.

For other hosts, install `requirements.txt` and start with:

```bash
uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
```

## Five-minute demo script

1. Open the app in two browser windows and join `general` as Ada and Lin.
2. Show both names in the online list; type in one window to show the typing indicator in the other.
3. Send a message and show it arriving in both windows immediately.
4. Leave and rejoin as another name to show message history; close a window to show the presence list update.
5. Explain that messages persist in SQLite while presence and typing live in the service process. A multi-instance deployment would need shared presence/pub-sub (for example Redis) so users connected to different instances can see each other.

## MVP limits and next steps

This MVP has no accounts or authorization, and usernames are unique only while present in a room. Presence is per process, so run one service instance unless a shared event layer is added. A production follow-up should add authentication, rate limits, stronger operational monitoring, and shared presence/broadcasting.
