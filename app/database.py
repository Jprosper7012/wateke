import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_ROOMS = ("general", "football", "music")


def database_path() -> str:
    return os.getenv("DB_PATH", "chat.db")


def connect(path: str | None = None) -> sqlite3.Connection:
    db_path = path or database_path()
    if db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize(path: str | None = None) -> None:
    with connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS rooms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL
            );
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                room_id INTEGER NOT NULL REFERENCES rooms(id),
                username TEXT NOT NULL,
                text TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        connection.executemany(
            "INSERT OR IGNORE INTO rooms(name) VALUES (?)",
            [(name,) for name in DEFAULT_ROOMS],
        )


def get_rooms(path: str | None = None) -> list[str]:
    with connect(path) as connection:
        rows = connection.execute("SELECT name FROM rooms ORDER BY id").fetchall()
    return [row["name"] for row in rows]


def add_message(room: str, username: str, text: str, path: str | None = None) -> dict:
    with connect(path) as connection:
        cursor = connection.execute(
            """INSERT INTO messages(room_id, username, text, created_at)
               SELECT id, ?, ?, ? FROM rooms WHERE name = ?""",
            (username, text, datetime.now(timezone.utc).isoformat(), room),
        )
        row = connection.execute(
            "SELECT id, username, text, created_at FROM messages WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()
    if row is None:
        raise ValueError("Unknown room")
    return {"id": row["id"], "room": room, "username": row["username"],
            "text": row["text"], "created_at": row["created_at"]}


def get_history(room: str, limit: int = 50, path: str | None = None) -> list[dict]:
    with connect(path) as connection:
        rows = connection.execute(
            """SELECT m.id, r.name AS room, m.username, m.text, m.created_at
               FROM messages m JOIN rooms r ON r.id = m.room_id
               WHERE r.name = ? ORDER BY m.id DESC LIMIT ?""",
            (room, limit),
        ).fetchall()
    return [dict(row) for row in reversed(rows)]
