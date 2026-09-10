"""Immutable audit trail (doc §9.4). Every chat turn writes one record —
not optional, this is the compliance trail a BFSI audit expects.
SQLite for the POC; swap for DynamoDB in production (doc §4) without
touching the calling code by replacing this module's backend.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from app.models.schemas import AuditLogRecord

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "audit_log.sqlite3"


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            employee_id TEXT NOT NULL,
            session_id TEXT NOT NULL,
            question TEXT NOT NULL,
            record_json TEXT NOT NULL
        )
    """)
    return con


def write_audit_record(record: AuditLogRecord) -> None:
    con = _connect()
    try:
        con.execute(
            "INSERT INTO audit_log (timestamp, employee_id, session_id, question, record_json) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                record.timestamp.isoformat(),
                record.employee_id,
                record.session_id,
                record.question,
                record.model_dump_json(),
            ),
        )
        con.commit()
    finally:
        con.close()


def read_audit_records(limit: int = 100) -> list[dict]:
    con = _connect()
    try:
        rows = con.execute(
            "SELECT record_json FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        import json
        return [json.loads(r[0]) for r in rows]
    finally:
        con.close()
