from typing import Any

from pydantic import BaseModel, Field


class BrowserCloseSessionRequest(BaseModel):
    session_id: str
    delete: bool = False


class BrowserArrangeRunWindowsRequest(BaseModel):
    run_id: str
    session_ids: list[str] | None = None
    start_x: int = 0
    start_y: int = 0
    width: int = 500
    height: int = 950
    col: int = 3
    space_x: int = -200
    space_y: int = 0


class BrowserOpenedProfilesResponse(BaseModel):
    vendor: str
    profiles: list[dict[str, Any]] = Field(default_factory=list)


class HealthResponse(BaseModel):
    vendor: str
    ok: bool
