from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from threading import RLock
from typing import Any, Literal
from uuid import uuid4

from app.services.log_hub import log_event_hub, run_event_hub
from app.services.sqlite_store import sqlite_store

LogLevel = Literal["info", "warn", "error", "debug", "verbose"]


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(slots=True)
class TaskRunItemRecord:
    id: str
    item_index: int
    profile_id: str | None = None
    status: str = "pending"
    debug_address: str | None = None
    websocket_url: str | None = None
    pid: int | None = None
    seq: int | None = None
    message: str = ""
    error: str | None = None
    started_at: str | None = None
    finished_at: str | None = None


@dataclass(slots=True)
class TaskRunLogRecord:
    id: str
    level: LogLevel
    message: str
    timestamp: str
    item_id: str | None = None
    seq: int | None = None


@dataclass(slots=True)
class TaskRunRecord:
    id: str
    task_key: str
    task_name: str
    vendor: str
    status: str
    concurrency: int
    config: dict[str, Any]
    items: list[TaskRunItemRecord]
    logs: list[TaskRunLogRecord] = field(default_factory=list)
    result_json: list[dict[str, Any]] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now)
    started_at: str | None = None
    finished_at: str | None = None


class RunStore:
    def __init__(self) -> None:
        self._runs: dict[str, TaskRunRecord] = {
            run.id: run for run in (_run_from_dict(item) for item in sqlite_store.list_task_runs())
        }
        self._lock = RLock()
        self._stop_stale_active_runs()

    def _stop_stale_active_runs(self) -> None:
        stale_runs = [
            run
            for run in self._runs.values()
            if run.status in {"pending", "running", "stopping"}
        ]
        for run in stale_runs:
            self.mark_run_stopped(run.id, "后端进程已重启，旧任务已自动停止。")

    def create_run(
        self,
        task_key: str,
        task_name: str,
        vendor: str,
        concurrency: int,
        config: dict[str, Any],
        item_count: int,
    ) -> TaskRunRecord:
        run = TaskRunRecord(
            id=uuid4().hex,
            task_key=task_key,
            task_name=task_name,
            vendor=vendor,
            status="pending",
            concurrency=concurrency,
            config=config,
            items=[
                TaskRunItemRecord(id=uuid4().hex, item_index=index)
                for index in range(1, item_count + 1)
            ],
        )
        with self._lock:
            self._runs[run.id] = run
        event = self.to_dict(run)
        sqlite_store.save_task_run(event)
        run_event_hub.publish("runs", event)
        return run

    def list_runs(self) -> list[TaskRunRecord]:
        with self._lock:
            return sorted(self._runs.values(), key=lambda run: run.created_at, reverse=True)

    def get_run(self, run_id: str) -> TaskRunRecord:
        with self._lock:
            return self._runs[run_id]

    def get_active_run(self) -> TaskRunRecord | None:
        with self._lock:
            active_runs = [
                run
                for run in self._runs.values()
                if run.status in {"pending", "running", "stopping"}
            ]
            if not active_runs:
                return None
            return sorted(active_runs, key=lambda run: run.created_at, reverse=True)[0]

    def get_active_run_id(self) -> str | None:
        active_run = self.get_active_run()
        return active_run.id if active_run else None

    def add_run_item(self, run_id: str) -> TaskRunItemRecord:
        with self._lock:
            run = self._runs[run_id]
            next_index = max((item.item_index for item in run.items), default=0) + 1
            item = TaskRunItemRecord(id=uuid4().hex, item_index=next_index)
            run.items.append(item)
            event = self.to_dict(run)

        sqlite_store.save_task_run(event)
        run_event_hub.publish("runs", event)
        return item

    def add_run_item_if_work_available(
        self,
        run_id: str,
        config_key: str,
    ) -> TaskRunItemRecord | None:
        with self._lock:
            run = self._runs[run_id]
            source = str(run.config.get(config_key) or "")
            remaining_lines = sum(1 for line in source.splitlines() if line.strip())
            active_items = sum(
                1
                for item in run.items
                if item.status not in {"completed", "failed"}
            )
            if remaining_lines <= active_items:
                return None

            next_index = max((item.item_index for item in run.items), default=0) + 1
            item = TaskRunItemRecord(id=uuid4().hex, item_index=next_index)
            run.items.append(item)
            event = self.to_dict(run)

        sqlite_store.save_task_run(event)
        run_event_hub.publish("runs", event)
        return item

    def has_config_textarea_lines(self, run_id: str, config_key: str) -> bool:
        with self._lock:
            run = self._runs[run_id]
            source = str(run.config.get(config_key) or "")
            return any(line.strip() for line in source.splitlines())

    def mark_run_started(self, run_id: str) -> None:
        with self._lock:
            run = self._runs[run_id]
            run.status = "running"
            run.started_at = utc_now()
            event = self.to_dict(run)
        sqlite_store.save_task_run(event)
        run_event_hub.publish("runs", event)
        self.add_log(run_id, "info", "任务开始运行。")

    def mark_run_finished(self, run_id: str) -> None:
        with self._lock:
            run = self._runs[run_id]
            failed = sum(1 for item in run.items if item.status == "failed")
            run.status = "failed" if failed else "completed"
            run.finished_at = utc_now()
            event = self.to_dict(run)
        sqlite_store.save_task_run(event)
        run_event_hub.publish("runs", event)
        self.add_log(run_id, "info", f"任务运行结束，状态：{run.status}。")

    def mark_run_stopping(self, run_id: str) -> None:
        with self._lock:
            run = self._runs[run_id]
            if run.status in {"completed", "failed", "stopped"}:
                event = self.to_dict(run)
            else:
                run.status = "stopping"
                event = self.to_dict(run)
        sqlite_store.save_task_run(event)
        run_event_hub.publish("runs", event)
        self.add_log(run_id, "warn", "已请求停止任务，正在取消后续操作。")

    def mark_run_stopped(self, run_id: str, message: str = "任务已停止。") -> None:
        with self._lock:
            run = self._runs[run_id]
            run.status = "stopped"
            run.finished_at = utc_now()
            for item in run.items:
                if item.status not in {"completed", "failed", "stopped"}:
                    item.status = "stopped"
                    item.message = message
                    item.finished_at = utc_now()
            event = self.to_dict(run)
        sqlite_store.save_task_run(event)
        run_event_hub.publish("runs", event)
        self.add_log(run_id, "warn", message)

    def mark_item_started(self, run_id: str, item_id: str) -> None:
        item = self._find_item(run_id, item_id)
        item.status = "running"
        item.started_at = utc_now()
        item.message = "任务项开始运行。"
        self._publish_run(run_id)
        self.add_log(run_id, "debug", f"第 {item.item_index} 项：任务项开始运行。", item_id)

    def mark_item_profile_created(self, run_id: str, item_id: str, profile_id: str) -> None:
        item = self._find_item(run_id, item_id)
        item.profile_id = profile_id
        item.status = "opening"
        item.message = "临时浏览器窗口已创建。"
        self._publish_run(run_id)

    def mark_item_browser_opened(
        self,
        run_id: str,
        item_id: str,
        debug_address: str,
        websocket_url: str | None,
        pid: int | None,
        seq: int | None,
    ) -> None:
        item = self._find_item(run_id, item_id)
        item.status = "running"
        item.debug_address = debug_address
        item.websocket_url = websocket_url
        item.pid = pid
        item.seq = seq
        item.message = "浏览器窗口已打开。"
        _apply_item_seq_to_logs(run=self._runs[run_id], item_id=item_id, seq=seq)
        self._publish_run(run_id)
        self.add_log(run_id, "info", f"第 {item.item_index} 项：浏览器已打开，调试地址：{debug_address}。", item_id)

    def mark_item_closing(self, run_id: str, item_id: str) -> None:
        item = self._find_item(run_id, item_id)
        item.status = "closing"
        item.message = "正在关闭浏览器窗口。"
        self._publish_run(run_id)
        self.add_log(run_id, "debug", f"第 {item.item_index} 项：正在关闭浏览器窗口。", item_id)

    def mark_item_deleting(self, run_id: str, item_id: str) -> None:
        item = self._find_item(run_id, item_id)
        item.status = "deleting"
        item.message = "正在删除临时浏览器窗口。"
        self._publish_run(run_id)
        self.add_log(run_id, "debug", f"第 {item.item_index} 项：正在删除临时浏览器窗口。", item_id)

    def mark_item_completed(self, run_id: str, item_id: str, message: str) -> None:
        item = self._find_item(run_id, item_id)
        item.status = "completed"
        item.message = message
        item.finished_at = utc_now()
        self._publish_run(run_id)

    def mark_item_failed(self, run_id: str, item_id: str, error: str) -> None:
        item = self._find_item(run_id, item_id)
        item.status = "failed"
        item.error = error
        item.finished_at = utc_now()
        self._publish_run(run_id)
        self.add_log(run_id, "error", f"第 {item.item_index} 项：{error}", item_id)

    def add_log(self, run_id: str, level: LogLevel, message: str, item_id: str | None = None) -> None:
        with self._lock:
            run = self._runs[run_id]
            seq = _item_seq(run, item_id)
            log = TaskRunLogRecord(
                id=uuid4().hex,
                level=level,
                message=_format_log_message_with_seq(message, seq),
                timestamp=utc_now(),
                item_id=item_id,
                seq=seq,
            )
            run.logs.append(log)
            event = self.to_dict(run)

        sqlite_store.save_task_run(event)
        log_event_hub.publish(run_id, asdict(log))

    def list_logs(self, run_id: str) -> list[TaskRunLogRecord]:
        with self._lock:
            return list(self._runs[run_id].logs)

    def list_run_profile_ids(self, run_id: str) -> list[str]:
        with self._lock:
            run = self._runs[run_id]
            return [
                item.profile_id
                for item in sorted(run.items, key=lambda current: current.item_index)
                if item.profile_id and item.debug_address and item.status not in {"pending", "failed", "completed", "deleting"}
            ]

    def reserve_config_textarea_line(
        self,
        run_id: str,
        item_id: str,
        config_key: str,
    ) -> dict[str, str]:
        with self._lock:
            run = self._runs[run_id]
            item = next(current for current in run.items if current.id == item_id)
            source = str(run.config.get(config_key) or "")
            lines = [line.strip() for line in source.splitlines() if line.strip()]
            if not lines:
                raise ValueError(f"{config_key} 没有可用配置行。")

            selected_line = lines[0]
            remaining_lines = lines[1:]
            run.config[config_key] = "\n".join(remaining_lines)

            result_id = uuid4().hex
            run.result_json.append(
                {
                    "id": result_id,
                    "type": "config_line",
                    "key": config_key,
                    "item_id": item_id,
                    "item_index": item.item_index,
                    "status": "reserved",
                    "line": _mask_config_line(config_key, selected_line),
                    "reserved_at": utc_now(),
                }
            )
            event = self.to_dict(run)

        sqlite_store.save_task_run(event)
        run_event_hub.publish("runs", event)
        return {
            "id": result_id,
            "line": selected_line,
        }

    def update_result_json(
        self,
        run_id: str,
        result_id: str,
        status: str,
        message: str = "",
        extra: dict[str, Any] | None = None,
    ) -> None:
        with self._lock:
            run = self._runs[run_id]
            result = next(
                (current for current in run.result_json if current.get("id") == result_id),
                None,
            )
            if result is None:
                return

            result["status"] = status
            result["finished_at"] = utc_now()
            if message:
                result["message"] = message
            if extra:
                result.update(extra)
            event = self.to_dict(run)

        sqlite_store.save_task_run(event)
        run_event_hub.publish("runs", event)

    def to_dict(self, run: TaskRunRecord) -> dict[str, Any]:
        data = asdict(run)
        data["total"] = len(run.items)
        data["completed"] = sum(1 for item in run.items if item.status == "completed")
        data["failed"] = sum(1 for item in run.items if item.status == "failed")
        return data

    def _find_item(self, run_id: str, item_id: str) -> TaskRunItemRecord:
        with self._lock:
            run = self._runs[run_id]
            return next(item for item in run.items if item.id == item_id)

    def _publish_run(self, run_id: str) -> None:
        with self._lock:
            run = self._runs[run_id]
            event = self.to_dict(run)
        sqlite_store.save_task_run(event)
        run_event_hub.publish("runs", event)


def _run_from_dict(data: dict[str, Any]) -> TaskRunRecord:
    items = [
        TaskRunItemRecord(
            id=str(item["id"]),
            item_index=int(item["item_index"]),
            profile_id=item.get("profile_id"),
            status=str(item.get("status") or "pending"),
            debug_address=item.get("debug_address"),
            websocket_url=item.get("websocket_url"),
            pid=item.get("pid"),
            seq=_coerce_optional_int(item.get("seq")),
            message=str(item.get("message") or ""),
            error=item.get("error"),
            started_at=item.get("started_at"),
            finished_at=item.get("finished_at"),
        )
        for item in data.get("items", [])
    ]
    logs = [
        TaskRunLogRecord(
            id=str(log["id"]),
            level=log.get("level", "info"),
            message=str(log.get("message") or ""),
            timestamp=str(log.get("timestamp") or utc_now()),
            item_id=log.get("item_id"),
            seq=_coerce_optional_int(log.get("seq")),
        )
        for log in data.get("logs", [])
    ]
    return TaskRunRecord(
        id=str(data["id"]),
        task_key=str(data["task_key"]),
        task_name=str(data["task_name"]),
        vendor=str(data["vendor"]),
        status=str(data.get("status") or "pending"),
        concurrency=int(data.get("concurrency") or 1),
        config=dict(data.get("config") or {}),
        items=items,
        logs=logs,
        result_json=list(data.get("result_json") or []),
        created_at=str(data.get("created_at") or utc_now()),
        started_at=data.get("started_at"),
        finished_at=data.get("finished_at"),
    )


def _mask_config_line(config_key: str, line: str) -> str:
    if config_key != "cards":
        return line

    parts = [part.strip() for part in line.split("|")]
    if not parts:
        return line

    number = parts[0]
    if len(number) >= 8:
        parts[0] = f"{number[:4]}{'*' * max(len(number) - 8, 0)}{number[-4:]}"
    elif len(number) >= 4:
        parts[0] = f"{'*' * max(len(number) - 4, 0)}{number[-4:]}"

    if len(parts) >= 3:
        parts[2] = "***"

    return "|".join(parts)


def _item_seq(run: TaskRunRecord, item_id: str | None) -> int | None:
    if not item_id:
        return None

    item = next((current for current in run.items if current.id == item_id), None)
    if item is None:
        return None
    return item.seq


def _format_log_message_with_seq(message: str, seq: int | None) -> str:
    if seq is None:
        return message
    if message.startswith(f"窗口[{seq}]-"):
        return message
    return f"窗口[{seq}]- {message}"


def _apply_item_seq_to_logs(run: TaskRunRecord, item_id: str, seq: int | None) -> None:
    if seq is None:
        return

    for log in run.logs:
        if log.item_id != item_id:
            continue
        log.seq = seq
        log.message = _format_log_message_with_seq(log.message, seq)


def _coerce_optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


run_store = RunStore()
