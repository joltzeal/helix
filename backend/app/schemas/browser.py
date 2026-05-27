from pydantic import BaseModel, Field


class BrowserStartRequest(BaseModel):
    vendor: str = Field(default="bit_browser")
    profile_id: str
    args: list[str] = Field(default_factory=list)
    queue: bool = True
    ignore_default_urls: bool = False
    new_page_url: str | None = None


class BrowserStopRequest(BaseModel):
    vendor: str = Field(default="bit_browser")
    profile_id: str


class BrowserStatusRequest(BaseModel):
    vendor: str = Field(default="bit_browser")
    profile_id: str


class BrowserLaunchResponse(BaseModel):
    profile_id: str
    debug_address: str
    websocket_url: str | None = None
    driver_path: str | None = None
    core_version: str | None = None
    pid: int | None = None
    seq: int | None = None


class BrowserStatusResponse(BaseModel):
    profile_id: str
    status: str


class HealthResponse(BaseModel):
    vendor: str
    ok: bool
