"""SQLite persistence for pending web imports."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional


SCHEMA = """
CREATE TABLE IF NOT EXISTS imports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_type TEXT NOT NULL,
    source_ref TEXT NOT NULL,
    doc_url TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    rows_json TEXT NOT NULL,
    warnings_json TEXT NOT NULL,
    import_log TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(source_type, source_ref)
);
"""


class ImportStore:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    def create_import(self, source_type: str, source_ref: str, rows: List[Dict], warnings: Iterable[str], doc_url: str | None = None) -> int:
        now = _now()
        try:
            with self.connect() as conn:
                cursor = conn.execute(
                    """
                    INSERT INTO imports (source_type, source_ref, doc_url, status, rows_json, warnings_json, created_at, updated_at)
                    VALUES (?, ?, ?, 'pending', ?, ?, ?, ?)
                    """,
                    (source_type, source_ref, doc_url, json.dumps(rows), json.dumps(list(warnings)), now, now),
                )
                return int(cursor.lastrowid)
        except sqlite3.IntegrityError:
            existing = self.get_by_source(source_type, source_ref)
            if existing is None:
                raise
            return int(existing["id"])

    def list_imports(self, limit: int = 50) -> List[Dict]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM imports ORDER BY datetime(created_at) DESC, id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._decode(row) for row in rows]

    def get_import(self, import_id: int) -> Optional[Dict]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM imports WHERE id = ?", (import_id,)).fetchone()
        return self._decode(row) if row else None

    def get_by_source(self, source_type: str, source_ref: str) -> Optional[Dict]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM imports WHERE source_type = ? AND source_ref = ?",
                (source_type, source_ref),
            ).fetchone()
        return self._decode(row) if row else None

    def update_rows(self, import_id: int, rows: List[Dict], warnings: Iterable[str]) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE imports SET rows_json = ?, warnings_json = ?, updated_at = ? WHERE id = ?",
                (json.dumps(rows), json.dumps(list(warnings)), _now(), import_id),
            )

    def update_status(self, import_id: int, status: str, import_log: str | None = None) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE imports SET status = ?, import_log = ?, updated_at = ? WHERE id = ?",
                (status, import_log, _now(), import_id),
            )

    def _decode(self, row: sqlite3.Row) -> Dict:
        data = dict(row)
        data["rows"] = json.loads(data.pop("rows_json"))
        data["warnings"] = json.loads(data.pop("warnings_json"))
        return data


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
