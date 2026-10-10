from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any
from modules.settings import DATA_DIR


DB_PATH = DATA_DIR / "db" / "history.sqlite3"


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS qa_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                sources TEXT NOT NULL,
                create_time DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()


def save_record(question: str, answer: str, sources: list[dict[str, Any]]) -> int:
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute(
            "INSERT INTO qa_history (question, answer, sources) VALUES (?, ?, ?)",
            (question, answer, json.dumps(sources, ensure_ascii=False)),
        )
        conn.commit()
        return int(cursor.lastrowid)


def list_history(limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT id, question, answer, sources, create_time
            FROM qa_history
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    records: list[dict[str, Any]] = []
    for row in rows:
        record = dict(row)
        try:
            record["sources"] = json.loads(record["sources"])
        except json.JSONDecodeError:
            record["sources"] = []
        records.append(record)
    return records


def clear_history() -> None:
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM qa_history")
        conn.commit()


def count_history() -> int:
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        return int(conn.execute("SELECT COUNT(*) FROM qa_history").fetchone()[0])
