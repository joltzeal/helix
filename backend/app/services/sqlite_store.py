from __future__ import annotations

import json
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from typing import Any

from app.core.paths import get_data_dir


class SQLiteStore:
    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or _default_db_path()
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
            self._strip_logs_from_task_runs(connection)
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
        stored_run = dict(run)
        stored_run.pop("logs", None)
        payload = json.dumps(stored_run, ensure_ascii=False)
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

    def _strip_logs_from_task_runs(self, connection: sqlite3.Connection) -> None:
        rows = connection.execute(
            "SELECT id, data_json FROM task_runs WHERE data_json LIKE '%\"logs\"%'"
        ).fetchall()
        for row in rows:
            try:
                payload = json.loads(str(row["data_json"]))
            except json.JSONDecodeError:
                continue
            if "logs" not in payload:
                continue
            payload.pop("logs", None)
            connection.execute(
                "UPDATE task_runs SET data_json = ? WHERE id = ?",
                (json.dumps(payload, ensure_ascii=False), row["id"]),
            )

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


def _default_db_path() -> Path:
    if data_dir := os.getenv("UCARD_DATA_DIR"):
        return Path(data_dir) / "helix.sqlite3"

    return get_data_dir() / "helix.sqlite3"


sqlite_store = SQLiteStore()


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()
