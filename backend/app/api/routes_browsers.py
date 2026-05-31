from fastapi import APIRouter, HTTPException

from app.fingerprint_browsers.ads_power import AdsPowerError
from app.fingerprint_browsers.bit_browser import BitBrowserError
from app.fingerprint_browsers.factory import create_fingerprint_browser_client
from app.task_modules.base import BrowserArrangeOptions
from app.schemas.browser import (
    BrowserArrangeRunWindowsRequest,
    BrowserCloseSessionRequest,
    BrowserOpenedProfilesResponse,
    HealthResponse,
)
from app.services.browser_sessions import browser_session_service
from app.services.runtime_store import runtime_store

router = APIRouter(prefix="/api/browsers", tags=["browsers"])


@router.post("/health/{vendor}", response_model=HealthResponse)
async def check_browser_health(vendor: str) -> HealthResponse:
    client = create_fingerprint_browser_client(vendor)
    try:
        ok = await client.health_check()
    except (BitBrowserError, AdsPowerError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return HealthResponse(vendor=vendor, ok=ok)


@router.get("/opened/{vendor}", response_model=BrowserOpenedProfilesResponse)
async def list_opened_profiles(vendor: str) -> BrowserOpenedProfilesResponse:
    client = create_fingerprint_browser_client(vendor)
    try:
        profiles = await client.list_open_profiles()
    except (BitBrowserError, AdsPowerError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return BrowserOpenedProfilesResponse(vendor=vendor, profiles=profiles)


@router.post("/sessions/close")
async def close_browser_session(payload: BrowserCloseSessionRequest) -> dict[str, bool]:
    try:
        session = runtime_store.get_session(payload.session_id)
        run = runtime_store.get_run(session.run_id)
        await browser_session_service.close_session(payload.session_id, delete=payload.delete, task_key=run.task_key)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Browser session not found.") from exc
    except (BitBrowserError, AdsPowerError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"ok": True}


@router.post("/runs/arrange-windows")
async def arrange_run_browser_windows(payload: BrowserArrangeRunWindowsRequest) -> dict[str, bool]:
    try:
        run = runtime_store.get_run(payload.run_id)
        await browser_session_service.arrange_run(
            payload.run_id,
            vendor=run.vendor,
            session_ids=payload.session_ids,
            options=BrowserArrangeOptions(
                start_x=payload.start_x,
                start_y=payload.start_y,
                width=payload.width,
                height=payload.height,
                col=payload.col,
                space_x=payload.space_x,
                space_y=payload.space_y,
            ),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Task run not found.") from exc
    except (BitBrowserError, AdsPowerError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"ok": True}
