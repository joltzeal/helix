from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal


RunStatus = Literal["pending", "running", "stopping", "completed", "failed", "cancelled"]
WorkItemStatus = Literal["pending", "running", "completed", "failed", "cancelled"]
BrowserSessionStatus = Literal["creating", "opening", "running", "closing", "closed", "deleted", "failed"]
LogLevel = Literal["info", "warn", "error", "debug", "verbose"]


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(slots=True)
class WorkItemRecord:
    id: str
    run_id: str
    index: int
    key: str
    label: str
    input: dict[str, Any]
    status: WorkItemStatus = "pending"
    message: str = ""
    error: str | None = None
    started_at: str | None = None
    finished_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class TaskRunRecord:
    id: str
    task_key: str
    task_name: str
    vendor: str
    status: RunStatus
    concurrency: int
    config: dict[str, Any]
    cleanup_policy: str = "delete"
    items: list[WorkItemRecord] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now)
    started_at: str | None = None
    finished_at: str | None = None
    message: str = ""
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["total"] = len(self.items)
        data["completed"] = sum(1 for item in self.items if item.status == "completed")
        data["failed"] = sum(1 for item in self.items if item.status == "failed")
        data["cancelled"] = sum(1 for item in self.items if item.status == "cancelled")
        return data


@dataclass(slots=True)
class BrowserSessionRecord:
    id: str
    run_id: str
    work_item_id: str
    vendor: str
    profile_id: str
    status: BrowserSessionStatus
    debug_address: str = ""
    websocket_url: str | None = None
    pid: int | None = None
    seq: int | None = None
    created_by_core: bool = False
    cleanup_policy: str = "delete"
    raw: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)
    opened_at: str | None = None
    closed_at: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class TaskResultRecord:
    id: str
    run_id: str
    work_item_id: str
    key: str
    status: str
    data: dict[str, Any]
    message: str = ""
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class TaskArtifactRecord:
    id: str
    run_id: str
    work_item_id: str
    key: str
    kind: str
    name: str
    filename: str
    mime_type: str
    relative_path: str
    size_bytes: int
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class LogRecord:
    id: str
    run_id: str
    level: LogLevel
    message: str
    timestamp: str
    work_item_id: str | None = None
    browser_session_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
