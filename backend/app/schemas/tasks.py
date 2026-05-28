from typing import Any

from pydantic import BaseModel, Field


class TaskConfigFieldResponse(BaseModel):
    key: str
    label: str
    block: str = "general"
    field_type: str
    required: bool
    description: str = ""
    placeholder: str = ""
    default: Any = None
    options: list[str] = Field(default_factory=list)


class TaskResultBlockResponse(BaseModel):
    key: str
    label: str
    source_key: str
    description: str = ""


class TaskModuleResponse(BaseModel):
    key: str
    name: str
    description: str
    config_fields: list[TaskConfigFieldResponse]
    result_blocks: list[TaskResultBlockResponse] = Field(default_factory=list)


class PluginModuleResponse(BaseModel):
    key: str
    name: str
    version: str = ""
    description: str = ""
    entry: str = ""
    status: str
    error: str = ""


class TaskRunCreateRequest(BaseModel):
    task_key: str
    vendor: str = "bit_browser"
    concurrency: int = Field(default=1, ge=1, le=20)
    config: dict[str, Any] = Field(default_factory=dict)


class TaskConfigurationResponse(BaseModel):
    task_key: str
    config: dict[str, Any] = Field(default_factory=dict)


class TaskConfigurationSaveRequest(BaseModel):
    config: dict[str, Any] = Field(default_factory=dict)


class TaskRunItemResponse(BaseModel):
    id: str
    item_index: int
    profile_id: str | None = None
    status: str
    debug_address: str | None = None
    websocket_url: str | None = None
    pid: int | None = None
    seq: int | None = None
    message: str = ""
    error: str | None = None
    started_at: str | None = None
    finished_at: str | None = None


class TaskRunLogResponse(BaseModel):
    id: str
    level: str
    message: str
    timestamp: str
    item_id: str | None = None
    seq: int | None = None


class TaskRunResponse(BaseModel):
    id: str
    task_key: str
    task_name: str
    vendor: str
    status: str
    concurrency: int
    total: int
    completed: int
    failed: int
    config: dict[str, Any]
    items: list[TaskRunItemResponse]
    logs: list[TaskRunLogResponse] = Field(default_factory=list)
    result_json: list[dict[str, Any]] = Field(default_factory=list)
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
