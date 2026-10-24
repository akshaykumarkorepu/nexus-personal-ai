"""SQLite persistence for conversations.

Two parallel logs are kept per conversation:

* ``api_messages`` - the exact provider transcript (content blocks stored verbatim,
  including thinking blocks and tool calls). It is strictly append-only: earlier
  rows are never edited, so replayed thinking blocks stay valid and the prompt
  cache keeps working.
* ``chat_messages`` - what the UI renders: ordered text and tool-activity parts,
  plus a status (``streaming``, ``complete``, ``stopped``, ``error``).
"""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id            TEXT PRIMARY KEY,
    title         TEXT NOT NULL,
    system_prompt TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS api_messages (
    seq             INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content_json    TEXT NOT NULL,
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_api_messages_conv ON api_messages(conversation_id, seq);
CREATE TABLE IF NOT EXISTS chat_messages (
    id              TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    parts_json      TEXT NOT NULL,
    status          TEXT NOT NULL,
    error           TEXT,
    provider        TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chat_messages_conv ON chat_messages(conversation_id, created_at);
"""


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def new_id() -> str:
    return uuid.uuid4().hex


class Store:
    def __init__(self, path: Path) -> None:
        self.path = path
        if str(path) != ":memory:":
            path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock:
            self._conn.execute("PRAGMA foreign_keys = ON")
            self._conn.execute("PRAGMA journal_mode = WAL")
            self._conn.executescript(SCHEMA)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            self._conn.execute("BEGIN")
            try:
                yield self._conn
            except BaseException:
                self._conn.execute("ROLLBACK")
                raise
            else:
                self._conn.execute("COMMIT")

    def ping(self) -> bool:
        with self._lock:
            return self._conn.execute("SELECT 1").fetchone() is not None

    # --- conversations -------------------------------------------------------

    def create_conversation(self, title: str, system_prompt: str) -> dict[str, Any]:
        cid, ts = new_id(), now_iso()
        with self._tx() as c:
            c.execute(
                "INSERT INTO conversations (id, title, system_prompt, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (cid, title, system_prompt, ts, ts),
            )
        conv = self.get_conversation(cid)
        assert conv is not None
        return conv

    def get_conversation(self, cid: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM conversations WHERE id = ?", (cid,)).fetchone()
        return dict(row) if row else None

    def list_conversations(self, limit: int = 200) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT c.id, c.title, c.created_at, c.updated_at,"
                " (SELECT COUNT(*) FROM chat_messages m WHERE m.conversation_id = c.id)"
                "   AS message_count"
                " FROM conversations c ORDER BY c.updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def rename_conversation(self, cid: str, title: str) -> bool:
        with self._tx() as c:
            cur = c.execute(
                "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
                (title, now_iso(), cid),
            )
        return cur.rowcount > 0

    def delete_conversation(self, cid: str) -> bool:
        with self._tx() as c:
            cur = c.execute("DELETE FROM conversations WHERE id = ?", (cid,))
        return cur.rowcount > 0

    def touch_conversation(self, cid: str) -> None:
        with self._tx() as c:
            c.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (now_iso(), cid))

    # --- provider transcript (append-only) -----------------------------------

    def append_api_messages(self, cid: str, messages: list[dict[str, Any]]) -> None:
        """Append one or more provider messages atomically."""
        ts = now_iso()
        with self._tx() as c:
            c.executemany(
                "INSERT INTO api_messages (conversation_id, role, content_json, created_at)"
                " VALUES (?, ?, ?, ?)",
                [(cid, m["role"], json.dumps(m["content"]), ts) for m in messages],
            )

    def get_api_messages(self, cid: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT role, content_json FROM api_messages WHERE conversation_id = ?"
                " ORDER BY seq",
                (cid,),
            ).fetchall()
        return [{"role": r["role"], "content": json.loads(r["content_json"])} for r in rows]

    # --- UI messages ---------------------------------------------------------

    def add_chat_message(
        self,
        cid: str,
        role: str,
        parts: list[dict[str, Any]],
        status: str,
        provider: str | None = None,
    ) -> dict[str, Any]:
        mid, ts = new_id(), now_iso()
        with self._tx() as c:
            c.execute(
                "INSERT INTO chat_messages"
                " (id, conversation_id, role, parts_json, status, provider, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (mid, cid, role, json.dumps(parts), status, provider, ts, ts),
            )
            c.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (ts, cid))
        return {
            "id": mid,
            "conversation_id": cid,
            "role": role,
            "parts": parts,
            "status": status,
            "error": None,
            "provider": provider,
            "created_at": ts,
            "updated_at": ts,
        }

    def update_chat_message(
        self,
        mid: str,
        parts: list[dict[str, Any]],
        status: str,
        error: str | None = None,
    ) -> None:
        with self._tx() as c:
            c.execute(
                "UPDATE chat_messages SET parts_json = ?, status = ?, error = ?, updated_at = ?"
                " WHERE id = ?",
                (json.dumps(parts), status, error, now_iso(), mid),
            )

    def get_chat_messages(self, cid: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM chat_messages WHERE conversation_id = ? ORDER BY created_at, rowid",
                (cid,),
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["parts"] = json.loads(d.pop("parts_json"))
            out.append(d)
        return out

    def mark_interrupted_streams(self) -> int:
        """On startup, any message still 'streaming' was cut off by a restart."""
        with self._tx() as c:
            cur = c.execute(
                "UPDATE chat_messages SET status = 'stopped',"
                " error = COALESCE(error, 'Interrupted by a backend restart.')"
                " WHERE status = 'streaming'"
            )
        return cur.rowcount
