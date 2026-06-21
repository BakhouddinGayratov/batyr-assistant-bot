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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                chat_id INTEGER NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                PRIMARY KEY (chat_id, key)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                fact TEXT NOT NULL,
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


def set_setting(chat_id: int, key: str, value: str):
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO settings (chat_id, key, value) VALUES (?, ?, ?)
            ON CONFLICT(chat_id, key) DO UPDATE SET value = excluded.value
            """,
            (chat_id, key, value),
        )


def get_settings(chat_id: int) -> dict[str, str]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT key, value FROM settings WHERE chat_id = ?",
            (chat_id,),
        ).fetchall()
    return dict(rows)


def add_fact(chat_id: int, fact: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO facts (chat_id, fact) VALUES (?, ?)",
            (chat_id, fact),
        )


def get_facts(chat_id: int, limit: int = 30) -> list[str]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT fact FROM facts WHERE chat_id = ? ORDER BY id DESC LIMIT ?",
            (chat_id, limit),
        ).fetchall()
    return [r[0] for r in rows]


def clear_facts(chat_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM facts WHERE chat_id = ?", (chat_id,))
