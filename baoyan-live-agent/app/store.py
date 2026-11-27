import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class Store:
    def __init__(self, database: Path):
        self.database = database

    @contextmanager
    def connection(self):
        database = sqlite3.connect(self.database, timeout=15)
        database.row_factory = sqlite3.Row
        try:
            with database:
                yield database
        finally:
            database.close()

    def initialize(self):
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                  id TEXT PRIMARY KEY,
                  kind TEXT NOT NULL,
                  status TEXT NOT NULL,
                  action TEXT NOT NULL,
                  stage TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  error TEXT,
                  data TEXT NOT NULL
                )
            """)

    @staticmethod
    def decode(row):
        if row is None:
            return None
        task = dict(row)
        task.update(json.loads(task.pop("data")))
        return task

    def create(self, task_id: str, kind: str, form: dict):
        stamp = now()
        with self.connection() as db:
            db.execute(
                "INSERT INTO tasks VALUES(?, ?, 'queued', 'plan', '等待处理', ?, ?, NULL, ?)",
                (task_id, kind, stamp, stamp, json.dumps({"form": form}, ensure_ascii=False)),
            )
        return self.get(task_id)

    def get(self, task_id: str):
        with self.connection() as db:
            return self.decode(db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone())

    def list(self):
        with self.connection() as db:
            rows = db.execute("SELECT * FROM tasks ORDER BY updated_at DESC LIMIT 100").fetchall()
        return [self.decode(row) for row in rows]

    def claim(self):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM tasks WHERE status='queued' ORDER BY updated_at LIMIT 1").fetchone()
            if row is None:
                return None
            db.execute("UPDATE tasks SET status='running', updated_at=? WHERE id=?", (now(), row["id"]))
            return self.decode(row)

    def recover(self):
        with self.connection() as db:
            db.execute("""
                UPDATE tasks
                SET status='failed', stage='处理已中断', error='服务重启中断了任务。可以继续重试。', updated_at=?
                WHERE status='running'
            """, (now(),))

    def enqueue(self, task_id: str, action: str, allowed: tuple[str, ...], changes: dict):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
            if row is None or row["status"] not in allowed:
                return False
            data = json.loads(row["data"]) | changes
            db.execute("""
                UPDATE tasks SET status='queued', action=?, stage='等待处理', error=NULL, data=?, updated_at=?
                WHERE id=?
            """, (action, json.dumps(data, ensure_ascii=False), now(), task_id))
        return True

    def update(self, task_id, *, stage, status="running", error=None, **changes):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT data FROM tasks WHERE id=?", (task_id,)).fetchone()
            data = json.loads(row["data"]) | changes
            db.execute("""
                UPDATE tasks SET status=?, stage=?, error=?, data=?, updated_at=? WHERE id=?
            """, (status, stage, error, json.dumps(data, ensure_ascii=False), now(), task_id))
