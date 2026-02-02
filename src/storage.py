from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


def ensure_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS papers (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                source_path TEXT NOT NULL,
                stored_path TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                added_at TEXT NOT NULL,
                openai_file_id TEXT,
                vector_store_id TEXT,
                vector_store_file_id TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                question TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        _ensure_column(conn, "papers", "openai_file_id", "TEXT")
        _ensure_column(conn, "papers", "vector_store_id", "TEXT")
        _ensure_column(conn, "papers", "vector_store_file_id", "TEXT")
        conn.commit()


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, col_type: str) -> None:
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")


def record_run(db_path: Path, run_id: str, question: str, created_at: str) -> None:
    ensure_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO runs (run_id, question, created_at) VALUES (?, ?, ?)",
            (run_id, question, created_at),
        )
        conn.commit()


def record_paper(
    db_path: Path,
    paper_id: str,
    run_id: str,
    source_path: str,
    stored_path: str,
    sha256: str,
    added_at: str,
    openai_file_id: str | None = None,
    vector_store_id: str | None = None,
    vector_store_file_id: str | None = None,
) -> None:
    ensure_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO papers
            (id, run_id, source_path, stored_path, sha256, added_at, openai_file_id, vector_store_id, vector_store_file_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                paper_id,
                run_id,
                source_path,
                stored_path,
                sha256,
                added_at,
                openai_file_id,
                vector_store_id,
                vector_store_file_id,
            ),
        )
        conn.commit()


def list_papers(db_path: Path, run_id: str) -> list[dict[str, Any]]:
    ensure_db(db_path)
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT id, source_path, stored_path, sha256, added_at, openai_file_id, vector_store_id, vector_store_file_id FROM papers WHERE run_id = ?",
            (run_id,),
        ).fetchall()
    return [
        {
            "id": row[0],
            "source_path": row[1],
            "stored_path": row[2],
            "sha256": row[3],
            "added_at": row[4],
            "openai_file_id": row[5],
            "vector_store_id": row[6],
            "vector_store_file_id": row[7],
        }
        for row in rows
    ]
