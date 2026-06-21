import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_DIR = Path(os.environ.get("DATA_DIR", Path(__file__).parent))
DB_PATH = DB_DIR / "assistant.db"


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                description TEXT NOT NULL,
                due_at TEXT,
                done INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


def add_message(chat_id: int, role: str, content: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO messages (chat_id, role, content) VALUES (?, ?, ?)",
            (chat_id, role, content),
        )


def get_recent_messages(chat_id: int, limit: int = 12):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT role, content FROM messages WHERE chat_id = ? ORDER BY id DESC LIMIT ?",
            (chat_id, limit),
        ).fetchall()
    return list(reversed(rows))


def add_task(chat_id: int, description: str, due_at: str | None):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO tasks (chat_id, description, due_at) VALUES (?, ?, ?)",
            (chat_id, description, due_at),
        )


def get_open_tasks(chat_id: int):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, description, due_at FROM tasks WHERE chat_id = ? AND done = 0 ORDER BY id",
            (chat_id,),
        ).fetchall()
    return rows


def complete_task(chat_id: int, task_id: int):
    with get_conn() as conn:
        conn.execute(
            "UPDATE tasks SET done = 1 WHERE chat_id = ? AND id = ?",
            (chat_id, task_id),
        )
