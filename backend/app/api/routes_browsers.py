from fastapi import APIRouter, HTTPException

from app.fingerprint_browsers.base import BrowserLaunchOptions
from app.fingerprint_browsers.bit_browser import BitBrowserError
from app.fingerprint_browsers.factory import create_fingerprint_browser_client
from app.schemas.browser import (
    BrowserArrangeWindowsRequest,
    BrowserLaunchResponse,
    BrowserStartRequest,
    BrowserStatusRequest,
    BrowserStatusResponse,
    BrowserStopRequest,
    HealthResponse,
)

router = APIRouter(prefix="/api/browsers", tags=["browsers"])


@router.post("/health/{vendor}", response_model=HealthResponse)
async def check_browser_health(vendor: str) -> HealthResponse:
    client = create_fingerprint_browser_client(vendor)
    try:
        ok = await client.health_check()
    except BitBrowserError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return HealthResponse(vendor=vendor, ok=ok)


@router.post("/start", response_model=BrowserLaunchResponse)
async def start_browser_profile(payload: BrowserStartRequest) -> BrowserLaunchResponse:
    client = create_fingerprint_browser_client(payload.vendor)
    try:
        result = await client.start_profile(
            payload.profile_id,
            BrowserLaunchOptions(
                args=payload.args,
                queue=payload.queue,
                ignore_default_urls=payload.ignore_default_urls,
                new_page_url=payload.new_page_url,
            ),
        )
    except BitBrowserError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return BrowserLaunchResponse(
        profile_id=result.profile_id,
        debug_address=result.debug_address,
        websocket_url=result.websocket_url,
        driver_path=result.driver_path,
        core_version=result.core_version,
        pid=result.pid,
        seq=result.seq,
    )


@router.post("/stop")
async def stop_browser_profile(payload: BrowserStopRequest) -> dict[str, bool]:
    client = create_fingerprint_browser_client(payload.vendor)
    try:
        await client.stop_profile(payload.profile_id)
    except BitBrowserError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {"ok": True}


@router.post("/status", response_model=BrowserStatusResponse)
async def get_browser_profile_status(payload: BrowserStatusRequest) -> BrowserStatusResponse:
    client = create_fingerprint_browser_client(payload.vendor)
    try:
        status = await client.get_profile_status(payload.profile_id)
    except BitBrowserError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return BrowserStatusResponse(profile_id=payload.profile_id, status=status)


@router.post("/arrange-windows")
async def arrange_browser_windows(payload: BrowserArrangeWindowsRequest) -> dict[str, bool]:
    client = create_fingerprint_browser_client(payload.vendor)
    try:
        await client.arrange_windows(
            payload.profile_ids,
            start_x=payload.start_x,
            start_y=payload.start_y,
            width=payload.width,
            height=payload.height,
            col=payload.col,
            space_x=payload.space_x,
            space_y=payload.space_y,
        )
    except BitBrowserError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {"ok": True}
