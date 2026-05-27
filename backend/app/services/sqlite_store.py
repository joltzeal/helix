from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from typing import Any


class SQLiteStore:
    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or Path("runtime") / "u-card.sqlite3"
        self._lock = RLock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_db(self) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS task_configurations (
                    task_key TEXT PRIMARY KEY,
                    config_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS task_runs (
                    id TEXT PRIMARY KEY,
                    task_key TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    result_json TEXT NOT NULL DEFAULT '[]',
                    data_json TEXT NOT NULL
                )
                """
            )
            columns = {
                str(row["name"])
                for row in connection.execute("PRAGMA table_info(task_runs)").fetchall()
            }
            if "result_json" not in columns:
                connection.execute(
                    "ALTER TABLE task_runs ADD COLUMN result_json TEXT NOT NULL DEFAULT '[]'"
                )
            connection.commit()

    def save_task_configuration(self, task_key: str, config: dict[str, Any]) -> None:
        now = _utc_now()
        payload = json.dumps(config, ensure_ascii=False)
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO task_configurations (task_key, config_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(task_key) DO UPDATE SET
                    config_json = excluded.config_json,
                    updated_at = excluded.updated_at
                """,
                (task_key, payload, now),
            )
            connection.commit()

    def get_task_configuration(self, task_key: str) -> dict[str, Any]:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT config_json FROM task_configurations WHERE task_key = ?",
                (task_key,),
            ).fetchone()
        if not row:
            return {}
        return json.loads(str(row["config_json"]))

    def save_task_run(self, run: dict[str, Any]) -> None:
        now = _utc_now()
        payload = json.dumps(run, ensure_ascii=False)
        result_payload = json.dumps(run.get("result_json") or [], ensure_ascii=False)
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO task_runs (id, task_key, status, created_at, updated_at, result_json, data_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    task_key = excluded.task_key,
                    status = excluded.status,
                    updated_at = excluded.updated_at,
                    result_json = excluded.result_json,
                    data_json = excluded.data_json
                """,
                (
                    run["id"],
                    run["task_key"],
                    run["status"],
                    run["created_at"],
                    now,
                    result_payload,
                    payload,
                ),
            )
            connection.commit()

    def list_task_runs(self) -> list[dict[str, Any]]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT data_json, result_json FROM task_runs ORDER BY created_at DESC"
            ).fetchall()
        runs: list[dict[str, Any]] = []
        for row in rows:
            run = json.loads(str(row["data_json"]))
            run["result_json"] = json.loads(str(row["result_json"] or "[]"))
            runs.append(run)
        return runs


sqlite_store = SQLiteStore()


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()
