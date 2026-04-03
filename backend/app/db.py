from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .config import settings


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_storage() -> None:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)


def init_db() -> None:
    init_storage()
    with db_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS document_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id INTEGER NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (document_id) REFERENCES documents(id)
            );

            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                path TEXT NOT NULL,
                mime_type TEXT NOT NULL,
                uploaded_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id INTEGER NOT NULL,
                chunk_index INTEGER NOT NULL,
                text TEXT NOT NULL,
                start_offset INTEGER NOT NULL,
                end_offset INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (file_id) REFERENCES files(id)
            );

            CREATE TABLE IF NOT EXISTS chat_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id TEXT NOT NULL,
                user_message TEXT NOT NULL,
                assistant_message TEXT NOT NULL,
                model TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )


def ensure_default_document() -> dict[str, Any]:
    with db_conn() as conn:
        row = conn.execute("SELECT * FROM documents ORDER BY id ASC LIMIT 1").fetchone()
        if row:
            return dict(row)

        now = utc_now()
        cur = conn.execute(
            "INSERT INTO documents (title, content, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (
                "Loomin Collaborative Document",
                "<h2>Loomin Docs Workspace</h2><p>Start writing collaboratively.</p>",
                now,
                now,
            ),
        )
        doc_id = int(cur.lastrowid)
        conn.execute(
            "INSERT INTO document_versions (document_id, content, created_at) VALUES (?, ?, ?)",
            (doc_id, "<h2>Loomin Docs Workspace</h2><p>Start writing collaboratively.</p>", now),
        )
        row = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
    return dict(row)


@contextmanager
def db_conn() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(Path(settings.db_path))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def insert_file(filename: str, path: str, mime_type: str) -> int:
    with db_conn() as conn:
        cur = conn.execute(
            "INSERT INTO files (filename, path, mime_type, uploaded_at) VALUES (?, ?, ?, ?)",
            (filename, path, mime_type, utc_now()),
        )
        return int(cur.lastrowid)


def list_files() -> list[dict[str, Any]]:
    with db_conn() as conn:
        rows = conn.execute("SELECT * FROM files ORDER BY id DESC").fetchall()
    return [dict(row) for row in rows]


def get_file(file_id: int) -> dict[str, Any] | None:
    with db_conn() as conn:
        row = conn.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
    return dict(row) if row else None


def delete_file(file_id: int) -> bool:
    with db_conn() as conn:
        cur = conn.execute("DELETE FROM files WHERE id = ?", (file_id,))
    return cur.rowcount > 0


def delete_chunks_for_file(file_id: int) -> None:
    with db_conn() as conn:
        conn.execute("DELETE FROM chunks WHERE file_id = ?", (file_id,))


def insert_chunk(
    file_id: int,
    chunk_index: int,
    text: str,
    start_offset: int,
    end_offset: int,
) -> int:
    with db_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO chunks (file_id, chunk_index, text, start_offset, end_offset, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (file_id, chunk_index, text, start_offset, end_offset, utc_now()),
        )
        return int(cur.lastrowid)


def get_all_chunks() -> list[dict[str, Any]]:
    with db_conn() as conn:
        rows = conn.execute("SELECT id, text FROM chunks ORDER BY id ASC").fetchall()
    return [dict(row) for row in rows]


def get_chunk(chunk_id: int) -> dict[str, Any] | None:
    with db_conn() as conn:
        row = conn.execute(
            """
            SELECT c.id, c.file_id, c.text, f.filename
            FROM chunks c
            JOIN files f ON f.id = c.file_id
            WHERE c.id = ?
            """,
            (chunk_id,),
        ).fetchone()
    return dict(row) if row else None


def save_chat(
    request_id: str,
    user_message: str,
    assistant_message: str,
    model: str,
    metadata: dict[str, Any],
) -> None:
    with db_conn() as conn:
        conn.execute(
            """
            INSERT INTO chat_history (request_id, user_message, assistant_message, model, metadata_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (request_id, user_message, assistant_message, model, json.dumps(metadata), utc_now()),
        )


def list_chat(limit: int = 50) -> list[dict[str, Any]]:
    with db_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM chat_history ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    data: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["metadata"] = json.loads(item.pop("metadata_json"))
        data.append(item)
    return data


def upsert_document(doc_id: int | None, title: str, content: str) -> dict[str, Any]:
    now = utc_now()
    with db_conn() as conn:
        if doc_id:
            conn.execute(
                "UPDATE documents SET title = ?, content = ?, updated_at = ? WHERE id = ?",
                (title, content, now, doc_id),
            )
            target_id = doc_id
        else:
            cur = conn.execute(
                "INSERT INTO documents (title, content, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (title, content, now, now),
            )
            target_id = int(cur.lastrowid)

        conn.execute(
            "INSERT INTO document_versions (document_id, content, created_at) VALUES (?, ?, ?)",
            (target_id, content, now),
        )
        row = conn.execute("SELECT * FROM documents WHERE id = ?", (target_id,)).fetchone()
    return dict(row)


def touch_document_content(doc_id: int, content: str) -> dict[str, Any] | None:
    with db_conn() as conn:
        current = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
        if not current:
            return None
        now = utc_now()
        conn.execute(
            "UPDATE documents SET content = ?, updated_at = ? WHERE id = ?",
            (content, now, doc_id),
        )
        conn.execute(
            "INSERT INTO document_versions (document_id, content, created_at) VALUES (?, ?, ?)",
            (doc_id, content, now),
        )
        row = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
    return dict(row)


def list_documents() -> list[dict[str, Any]]:
    with db_conn() as conn:
        rows = conn.execute("SELECT * FROM documents ORDER BY updated_at DESC").fetchall()
    return [dict(row) for row in rows]


def get_document(doc_id: int) -> dict[str, Any] | None:
    with db_conn() as conn:
        row = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
    return dict(row) if row else None


def list_document_versions(doc_id: int) -> list[dict[str, Any]]:
    with db_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM document_versions WHERE document_id = ? ORDER BY id DESC", (doc_id,)
        ).fetchall()
    return [dict(row) for row in rows]
