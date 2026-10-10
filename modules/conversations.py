"""Conversation isolation with atomic turn persistence; legacy history is untouched."""
import json
import sqlite3
import uuid
from contextlib import contextmanager

from modules.settings import DATA_DIR, get_settings

DB_PATH = DATA_DIR / "db" / "conversations.sqlite3"


@contextmanager
def connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH, timeout=15) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        db.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY, title TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS turns (
                id INTEGER PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                question TEXT NOT NULL, response TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        """)
        yield db


def create_session(title: str = "新会话") -> dict:
    session_id = uuid.uuid4().hex
    with connection() as db:
        db.execute("INSERT INTO sessions(id,title) VALUES (?,?)", (session_id, title))
    return {"id": session_id, "title": title}


def list_sessions() -> list[dict]:
    with connection() as db:
        return [dict(row) for row in db.execute("SELECT * FROM sessions ORDER BY updated_at DESC, rowid DESC")]


def get_turns(session_id: str) -> list[dict]:
    with connection() as db:
        if not db.execute("SELECT id FROM sessions WHERE id=?", (session_id,)).fetchone():
            raise KeyError("会话不存在")
        return [{**dict(row), "response": json.loads(row["response"])} for row in db.execute(
            "SELECT * FROM turns WHERE session_id=? ORDER BY id", (session_id,))]


def delete_session(session_id: str) -> int:
    with connection() as db:
        return db.execute("DELETE FROM sessions WHERE id=?", (session_id,)).rowcount


def rename_session(session_id: str, title: str) -> bool:
    with connection() as db:
        return bool(db.execute("UPDATE sessions SET title=? WHERE id=?", (title, session_id)).rowcount)


def save_turn(session_id: str, question: str, response: dict) -> None:
    with connection() as db:
        db.execute("INSERT INTO turns(session_id,question,response) VALUES (?,?,?)",
                   (session_id, question, json.dumps(response, ensure_ascii=False)))
        db.execute("UPDATE sessions SET title=CASE WHEN title='新会话' THEN ? ELSE title END, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                   (question[:40], session_id))


def history_messages(session_id: str) -> list[dict]:
    config = get_settings()
    turns = get_turns(session_id)
    if not config.history_turns or not config.history_chars:
        return []
    budget = config.history_chars
    messages = []
    for turn in reversed(turns[-config.history_turns:]):
        pair = [{"role": "user", "content": turn["question"]},
                {"role": "assistant", "content": turn["response"]["answer"]}]
        size = sum(len(message["content"]) for message in pair)
        if size > budget:
            break
        messages[0:0] = pair
        budget -= size
    return messages


def statistics() -> dict:
    with connection() as db:
        return {"sessions": db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0],
                "queries": db.execute("SELECT COUNT(*) FROM turns").fetchone()[0],
                "recent_queries": [dict(row) for row in db.execute(
                    "SELECT question,created_at,session_id FROM turns ORDER BY id DESC LIMIT 8")]}
