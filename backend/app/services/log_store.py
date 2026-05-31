from __future__ import annotations

import json
from collections import deque
from pathlib import Path
from uuid import uuid4

from app.core.paths import get_data_dir
from app.services.models import LogLevel, LogRecord, utc_now
from app.services.runtime_events import runtime_event_hub


class LogStore:
    async def add(
        self,
        run_id: str,
        level: LogLevel,
        message: str,
        *,
        work_item_id: str | None = None,
        browser_session_id: str | None = None,
    ) -> LogRecord:
        log = LogRecord(
            id=uuid4().hex,
            run_id=run_id,
            level=level,
            message=message,
            timestamp=utc_now(),
            work_item_id=work_item_id,
            browser_session_id=browser_session_id,
        )
        _append_jsonl(_log_file_path(run_id), log.to_dict())
        runtime_event_hub.publish(f"run:{run_id}:logs", log.to_dict())
        return log

    def list(self, run_id: str, *, limit: int | None = 1000) -> list[dict]:
        path = _log_file_path(run_id)
        if not path.exists():
            return []

        if limit and limit > 0:
            with path.open("r", encoding="utf-8") as file:
                lines = deque(file, maxlen=limit)
        else:
            with path.open("r", encoding="utf-8") as file:
                lines = list(file)

        logs: list[dict] = []
        for line in lines:
            if not line.strip():
                continue
            try:
                logs.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return logs


def get_run_dir(run_id: str) -> Path:
    return get_data_dir() / "runs" / run_id


def get_artifacts_dir(run_id: str, work_item_id: str) -> Path:
    return get_run_dir(run_id) / "artifacts" / work_item_id


def _log_file_path(run_id: str) -> Path:
    return get_run_dir(run_id) / "logs.jsonl"


def _append_jsonl(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
        file.write("\n")


log_store = LogStore()
