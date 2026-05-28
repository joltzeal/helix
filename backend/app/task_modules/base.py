from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal


TaskFieldType = Literal["text", "password", "number", "textarea", "select", "multi-select", "checkbox"]
LogLevel = Literal["info", "warn", "error", "debug", "verbose"]


@dataclass(slots=True)
class TaskConfigField:
    key: str
    label: str
    block: str = "general"
    field_type: TaskFieldType = "text"
    required: bool = False
    description: str = ""
    placeholder: str = ""
    default: Any = None
    options: list[str] = field(default_factory=list)


@dataclass(slots=True)
class TaskResultBlock:
    key: str
    label: str
    source_key: str
    description: str = ""


@dataclass(slots=True)
class TaskModuleManifest:
    key: str
    name: str
    description: str
    config_fields: list[TaskConfigField]
    result_blocks: list[TaskResultBlock] = field(default_factory=list)


@dataclass(slots=True)
class TaskExecutionContext:
    run_id: str
    item_id: str
    item_index: int
    vendor: str
    config: dict[str, Any]
    log: Callable[[LogLevel, str], None]
    mark_profile_created: Callable[[str], None]
    mark_browser_opened: Callable[[str, str | None, int | None, int | None], None]
    mark_browser_closing: Callable[[], None]
    mark_browser_deleting: Callable[[], None]
    list_run_profile_ids: Callable[[], list[str]] = field(default_factory=lambda: lambda: [])
    is_stopping: Callable[[], bool] = field(default_factory=lambda: lambda: False)
    raise_if_stopping: Callable[[], None] = field(default_factory=lambda: lambda: None)
    reserve_config_textarea_line: Callable[[str], dict[str, str]] = field(
        default_factory=lambda: lambda _key: {}
    )
    update_result_json: Callable[[str, str, str, dict[str, Any] | None], None] = field(
        default_factory=lambda: lambda _result_id, _status, _message="", _extra=None: None
    )
    reserved_config_lines: dict[str, dict[str, str]] = field(default_factory=dict)
    profile_id: str | None = None
    debug_address: str = ""
    browser_result: dict[str, Any] = field(default_factory=dict)
    browser_detail: dict[str, Any] = field(default_factory=dict)


class AutomationTaskModule(ABC):
    manifest: TaskModuleManifest

    def resolve_item_count(self, config: dict[str, Any]) -> int:
        return 1

    def dynamic_work_config_key(self) -> str | None:
        return None

    @abstractmethod
    async def run(self, context: TaskExecutionContext) -> dict[str, Any]:
        raise NotImplementedError
