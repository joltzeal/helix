from pydantic import BaseModel, ConfigDict, Field


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


class BrowserArrangeWindowsRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    vendor: str = Field(default="bit_browser")
    profile_ids: list[str] = Field(default_factory=list)
    start_x: int = Field(default=0, alias="startX")
    start_y: int = Field(default=0, alias="startY")
    width: int = Field(default=500, ge=1)
    height: int = Field(default=950, ge=1)
    col: int = Field(default=3, ge=1)
    space_x: int = Field(default=-200, alias="spaceX")
    space_y: int = Field(default=0, alias="spaceY")


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
