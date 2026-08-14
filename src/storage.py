"""本地 SQLite 持久化 + owner 删除权闭环。

铁律（来自架构「安全设计 / 部署设计」）：
- 本地单租户、可删除、无遥测、不出域
- tenant_id 作用域隔离；purge_owner 一键清除该 tenant 全部数据
"""
from __future__ import annotations

import os
import sqlite3
import json
import uuid
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Store:
    """封装本地 SQLite 存储，tenant 作用域隔离。"""

    def __init__(self, data_dir: str, tenant_id: str):
        self.data_dir = data_dir
        self.tenant_id = tenant_id
        os.makedirs(data_dir, exist_ok=True)
        self.db_path = os.path.join(data_dir, "interviews.db")
        self._init_db()

    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._conn() as c:
            c.executescript("""
            CREATE TABLE IF NOT EXISTS profiles (
                id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                name TEXT NOT NULL,
                raw_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS intakes (
                id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                name TEXT NOT NULL,
                raw_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS personas (
                id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                name TEXT NOT NULL,
                raw_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                profile_id TEXT NOT NULL,
                persona_id TEXT,
                scenario TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL,
                finished_at TEXT
            );
            CREATE TABLE IF NOT EXISTS turns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                phase TEXT,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS materials (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                name TEXT NOT NULL,
                provided INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                item_id TEXT NOT NULL,
                dimension TEXT NOT NULL,
                points INTEGER NOT NULL DEFAULT 0,
                reason TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS weaknesses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                category TEXT NOT NULL,
                detail TEXT NOT NULL,
                severity TEXT NOT NULL DEFAULT 'medium',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS reports (
                session_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_sessions_tenant ON sessions(tenant_id);
            CREATE INDEX IF NOT EXISTS idx_turns_session ON turns(session_id);
            CREATE INDEX IF NOT EXISTS idx_weak_tenant ON weaknesses(tenant_id);
            CREATE INDEX IF NOT EXISTS idx_scores_session ON scores(session_id);
            """)

    # ---- 画像 / 调查 ----
    def save_intake(self, name: str, raw: dict) -> str:
        iid = uuid.uuid4().hex
        with self._conn() as c:
            c.execute(
                "INSERT INTO intakes(id,tenant_id,name,raw_json,created_at) VALUES(?,?,?,?,?)",
                (iid, self.tenant_id, name, json.dumps(raw, ensure_ascii=False), _now()),
            )
        return iid

    def save_persona(self, name: str, raw: dict) -> str:
        pid = uuid.uuid4().hex
        with self._conn() as c:
            c.execute(
                "INSERT INTO personas(id,tenant_id,name,raw_json,created_at) VALUES(?,?,?,?,?)",
                (pid, self.tenant_id, name, json.dumps(raw, ensure_ascii=False), _now()),
            )
        return pid

    # ---- 资料 / 画像关联 ----
    def save_profile(self, name: str, raw: dict) -> str:
        pid = uuid.uuid4().hex
        with self._conn() as c:
            c.execute(
                "INSERT INTO profiles(id,tenant_id,name,raw_json,created_at) VALUES(?,?,?,?,?)",
                (pid, self.tenant_id, name, json.dumps(raw, ensure_ascii=False), _now()),
            )
        return pid

    def create_session(self, profile_id: str, scenario: str, persona_id: str | None = None) -> str:
        sid = uuid.uuid4().hex
        with self._conn() as c:
            c.execute(
                "INSERT INTO sessions(id,tenant_id,profile_id,persona_id,scenario,status,created_at) VALUES(?,?,?,?,?,?,?)",
                (sid, self.tenant_id, profile_id, persona_id, scenario, "active", _now()),
            )
        return sid

    def append_turn(self, session_id: str, role: str, content: str, phase: str | None = None):
        with self._conn() as c:
            c.execute(
                "INSERT INTO turns(session_id,role,phase,content,created_at) VALUES(?,?,?,?,?)",
                (session_id, role, phase, content, _now()),
            )

    def add_material(self, session_id: str, name: str, provided: bool):
        with self._conn() as c:
            c.execute(
                "INSERT INTO materials(id,session_id,tenant_id,name,provided,created_at) VALUES(?,?,?,?,?,?)",
                (uuid.uuid4().hex, session_id, self.tenant_id, name, 1 if provided else 0, _now()),
            )

    def get_materials(self, session_id: str):
        with self._conn() as c:
            rows = c.execute(
                "SELECT name,provided FROM materials WHERE session_id=?", (session_id,)
            ).fetchall()
        return [dict(r) for r in rows]

    def add_score(self, session_id: str, item_id: str, dimension: str, points: int, reason: str):
        with self._conn() as c:
            c.execute(
                "INSERT INTO scores(session_id,tenant_id,item_id,dimension,points,reason,created_at) VALUES(?,?,?,?,?,?,?)",
                (session_id, self.tenant_id, item_id, dimension, int(points), reason, _now()),
            )

    def get_scores(self, session_id: str):
        with self._conn() as c:
            rows = c.execute(
                "SELECT item_id,dimension,points,reason FROM scores WHERE session_id=?", (session_id,)
            ).fetchall()
        return [dict(r) for r in rows]

    def add_weakness(self, session_id: str, category: str, detail: str, severity: str = "medium"):
        with self._conn() as c:
            c.execute(
                "INSERT INTO weaknesses(tenant_id,session_id,category,detail,severity,created_at) VALUES(?,?,?,?,?,?)",
                (self.tenant_id, session_id, category, detail, severity, _now()),
            )

    def finish_session(self, session_id: str):
        with self._conn() as c:
            c.execute("UPDATE sessions SET status='finished', finished_at=? WHERE id=?", (_now(), session_id))

    def save_report(self, session_id: str, content: str):
        with self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO reports(session_id,tenant_id,content,created_at) VALUES(?,?,?,?)",
                (session_id, self.tenant_id, content, _now()),
            )

    def list_sessions(self):
        with self._conn() as c:
            rows = c.execute(
                "SELECT s.id,s.scenario,s.status,s.created_at,s.finished_at,p.name "
                "FROM sessions s JOIN profiles p ON p.id=s.profile_id "
                "WHERE s.tenant_id=? ORDER BY s.created_at DESC",
                (self.tenant_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_transcript(self, session_id: str):
        with self._conn() as c:
            rows = c.execute(
                "SELECT role,phase,content,created_at FROM turns WHERE session_id=? ORDER BY id ASC",
                (session_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_report(self, session_id: str):
        with self._conn() as c:
            row = c.execute("SELECT content FROM reports WHERE session_id=?", (session_id,)).fetchone()
        return row["content"] if row else None

    def resolve_session_id(self, prefix: str) -> str | None:
        """按前缀解析 session id（list 只显示前 8 位，便于引用）。"""
        with self._conn() as c:
            rows = c.execute(
                "SELECT id FROM sessions WHERE tenant_id=?", (self.tenant_id,)
            ).fetchall()
        for r in rows:
            if r["id"].startswith(prefix):
                return r["id"]
        return None

    def get_weaknesses(self, session_id: str | None = None):
        with self._conn() as c:
            if session_id:
                rows = c.execute(
                    "SELECT category,detail,severity,created_at FROM weaknesses "
                    "WHERE tenant_id=? AND session_id=? ORDER BY id ASC",
                    (self.tenant_id, session_id),
                ).fetchall()
            else:
                rows = c.execute(
                    "SELECT session_id,category,detail,severity,created_at FROM weaknesses "
                    "WHERE tenant_id=? ORDER BY id ASC",
                    (self.tenant_id,),
                ).fetchall()
        return [dict(r) for r in rows]

    def purge_owner(self) -> int:
        """owner 删除权闭环：清除该 tenant 全部记录。返回删除行数。"""
        total = 0
        with self._conn() as c:
            for tbl in ("profiles", "intakes", "personas", "sessions", "weaknesses",
                        "reports", "materials", "scores"):
                cur = c.execute(f"DELETE FROM {tbl} WHERE tenant_id=?", (self.tenant_id,))
                total += cur.rowcount
            cur = c.execute("DELETE FROM turns WHERE session_id NOT IN (SELECT id FROM sessions)")
            total += cur.rowcount
        return total
