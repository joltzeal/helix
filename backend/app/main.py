import asyncio
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes_browsers import router as browsers_router
from app.api.routes_task_modules import router as task_modules_router
from app.api.routes_tasks import router as tasks_router
from app.core.config import get_settings
from app.services.task_control import task_control


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:1420",
            "http://127.0.0.1:1420",
            "tauri://localhost",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(browsers_router)
    app.include_router(task_modules_router)
    app.include_router(tasks_router)

    @app.on_event("shutdown")
    async def stop_active_task_on_shutdown() -> None:
        await task_control.stop_on_shutdown()

    @app.get("/health")
    async def health() -> dict[str, bool]:
        return {"ok": True}

    @app.post("/shutdown")
    async def shutdown() -> dict[str, bool]:
        async def exit_process() -> None:
            await asyncio.sleep(0.2)
            os._exit(0)

        asyncio.create_task(exit_process())
        return {"ok": True}

    return app


app = create_app()
