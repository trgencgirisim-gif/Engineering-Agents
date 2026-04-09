"""shared/session_store.py — SQLite-based session persistence.

Thread-safe, WAL mode, JSON columns for complex fields.
Supports save/load/list/delete/cleanup of analysis sessions.
"""

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).parent.parent / "data" / "sessions.db"

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sessions (
    sid             TEXT PRIMARY KEY,
    brief           TEXT NOT NULL,
    enhanced_brief  TEXT DEFAULT '',
    domains         TEXT DEFAULT '[]',
    mode            INTEGER DEFAULT 4,
    max_rounds      INTEGER DEFAULT 3,
    domain_model    TEXT DEFAULT 'sonnet',
    status          TEXT DEFAULT 'prep',
    error           TEXT DEFAULT '',
    total_cost      REAL DEFAULT 0.0,
    total_input     INTEGER DEFAULT 0,
    total_output    INTEGER DEFAULT 0,
    cache_write_tokens  INTEGER DEFAULT 0,
    cache_read_tokens   INTEGER DEFAULT 0,
    cache_saved_usd     REAL DEFAULT 0.0,
    qa_questions    TEXT DEFAULT '[]',
    qa_answers      TEXT DEFAULT '{}',
    agent_log       TEXT DEFAULT '[]',
    round_scores    TEXT DEFAULT '[]',
    final_report    TEXT DEFAULT '',
    txt_output      TEXT DEFAULT '',
    blackboard_json TEXT DEFAULT '{}',
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now')),
    completed_at    TEXT DEFAULT NULL
);
CREATE INDEX IF NOT EXISTS idx_status ON sessions(status);
CREATE INDEX IF NOT EXISTS idx_created ON sessions(created_at);
"""

_JSON_FIELDS = ("domains", "qa_questions", "qa_answers",
                "agent_log", "round_scores", "blackboard_json")


class SessionStore:
    """Thread-safe SQLite session store."""

    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._ensure_schema()

    def _get_conn(self) -> sqlite3.Connection:
        """Per-thread connection (SQLite requirement)."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(
                str(self._db_path),
                check_same_thread=False,
                timeout=10.0,
            )
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA busy_timeout=5000")
            self._local.conn.row_factory = sqlite3.Row
        return self._local.conn

    def _ensure_schema(self):
        conn = self._get_conn()
        conn.executescript(_SCHEMA_SQL)
        conn.commit()

    # ── WRITE ───────────────────────────────────────────────

    def save(self, session) -> None:
        """Save/upsert a Session object to SQLite."""
        conn = self._get_conn()
        data = self._session_to_row(session)
        columns = ", ".join(data.keys())
        placeholders = ", ".join(f":{k}" for k in data)
        updates = ", ".join(
            f"{k}=excluded.{k}" for k in data if k != "sid"
        )
        sql = (
            f"INSERT INTO sessions ({columns}) VALUES ({placeholders}) "
            f"ON CONFLICT(sid) DO UPDATE SET {updates}, "
            f"updated_at=datetime('now')"
        )
        conn.execute(sql, data)
        conn.commit()

    def checkpoint(self, session) -> None:
        """Alias for save — semantic name for mid-analysis saves."""
        self.save(session)

    # ── READ ────────────────────────────────────────────────

    def load(self, sid: str) -> Optional[dict]:
        """Load a session by sid. Returns None if not found."""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM sessions WHERE sid = ?", (sid,)
        ).fetchone()
        if not row:
            return None
        return self._row_to_dict(row)

    def list_sessions(self, limit: int = 50, offset: int = 0,
                      status: str = None) -> list:
        """List sessions, newest first. Optional status filter."""
        conn = self._get_conn()
        sql = (
            "SELECT sid, brief, mode, status, total_cost, domains, "
            "created_at, completed_at, round_scores "
            "FROM sessions"
        )
        params: list = []
        if status:
            sql += " WHERE status = ?"
            params.append(status)
        sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = conn.execute(sql, params).fetchall()
        return [self._summary_from_row(r) for r in rows]

    def count(self, status: str = None) -> int:
        """Count sessions, optionally filtered by status."""
        conn = self._get_conn()
        if status:
            return conn.execute(
                "SELECT COUNT(*) FROM sessions WHERE status = ?", (status,)
            ).fetchone()[0]
        return conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]

    # ── DELETE ──────────────────────────────────────────────

    def delete(self, sid: str) -> bool:
        """Delete a session. Returns True if deleted."""
        conn = self._get_conn()
        cur = conn.execute("DELETE FROM sessions WHERE sid = ?", (sid,))
        conn.commit()
        return cur.rowcount > 0

    def cleanup(self, days: int = 30) -> int:
        """Delete sessions older than N days. Returns count deleted."""
        conn = self._get_conn()
        cur = conn.execute(
            "DELETE FROM sessions WHERE created_at < datetime('now', ?)",
            (f"-{days} days",),
        )
        conn.commit()
        return cur.rowcount

    # ── SERIALIZATION HELPERS ───────────────────────────────

    def _session_to_row(self, session) -> dict:
        """Convert a Session object to a flat dict for SQLite INSERT."""
        bb_json = "{}"
        if hasattr(session, "blackboard") and session.blackboard:
            try:
                bb_json = json.dumps(
                    session.blackboard.to_dict(), default=str
                )
            except Exception:
                bb_json = "{}"

        is_done = getattr(session, "status", "") == "done"
        return {
            "sid": session.sid,
            "brief": session.brief,
            "enhanced_brief": getattr(session, "enhanced_brief", ""),
            "domains": json.dumps(getattr(session, "domains", [])),
            "mode": session.mode,
            "max_rounds": session.max_rounds,
            "domain_model": getattr(session, "domain_model", "sonnet"),
            "status": getattr(session, "status", "prep"),
            "error": getattr(session, "error", ""),
            "total_cost": getattr(session, "total_cost", 0.0),
            "total_input": getattr(session, "total_input", 0),
            "total_output": getattr(session, "total_output", 0),
            "cache_write_tokens": getattr(session, "cache_write_tokens", 0),
            "cache_read_tokens": getattr(session, "cache_read_tokens", 0),
            "cache_saved_usd": getattr(session, "cache_saved_usd", 0.0),
            "qa_questions": json.dumps(
                getattr(session, "qa_questions", [])
            ),
            "qa_answers": json.dumps(
                getattr(session, "qa_answers", {}), default=str
            ),
            "agent_log": json.dumps(
                getattr(session, "agent_log", []), default=str
            ),
            "round_scores": json.dumps(
                getattr(session, "round_scores", [])
            ),
            "final_report": getattr(session, "final_report", ""),
            "txt_output": getattr(session, "txt_output", ""),
            "blackboard_json": bb_json,
            "completed_at": (
                datetime.now().isoformat() if is_done else None
            ),
        }

    def _row_to_dict(self, row) -> dict:
        """Convert a sqlite3.Row to a dict with JSON fields parsed."""
        d = dict(row)
        for field in _JSON_FIELDS:
            if field in d and isinstance(d[field], str):
                try:
                    d[field] = json.loads(d[field])
                except (json.JSONDecodeError, TypeError):
                    pass
        return d

    def _summary_from_row(self, row) -> dict:
        """Lightweight summary for listing endpoint."""
        d = dict(row)
        domains = d.get("domains", "[]")
        if isinstance(domains, str):
            try:
                domains = json.loads(domains)
            except (json.JSONDecodeError, TypeError):
                domains = []
        scores = d.get("round_scores", "[]")
        if isinstance(scores, str):
            try:
                scores = json.loads(scores)
            except (json.JSONDecodeError, TypeError):
                scores = []
        return {
            "sid": d["sid"],
            "brief": (d.get("brief") or "")[:200],
            "mode": d["mode"],
            "status": d["status"],
            "total_cost": d["total_cost"],
            "domains": (
                [{"key": k, "name": n} for k, n in domains]
                if domains else []
            ),
            "created_at": d["created_at"],
            "completed_at": d.get("completed_at"),
            "final_score": (
                scores[-1].get("puan") if scores else None
            ),
        }
