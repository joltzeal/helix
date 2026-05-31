from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect

from app.schemas.tasks import (
    TaskConfigurationResponse,
    TaskConfigurationSaveRequest,
    TaskModuleResponse,
    TaskRunCreateRequest,
    TaskRunLogResponse,
    TaskRunResponse,
)
from app.services.log_hub import log_event_hub, run_event_hub
from app.services.run_store import run_store
from app.services.sqlite_store import sqlite_store
from app.services.task_control import TaskControlError, task_control
from app.task_modules.registry import get_task_module, list_task_modules

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.get("", response_model=list[TaskModuleResponse])
async def list_tasks() -> list[TaskModuleResponse]:
    return [
        TaskModuleResponse(
            key=task.manifest.key,
            name=task.manifest.name,
            description=task.manifest.description,
            config_fields=[
                {
                    "key": field.key,
                    "label": field.label,
                    "block": field.block,
                    "field_type": field.field_type,
                    "required": field.required,
                    "description": field.description,
                    "placeholder": field.placeholder,
                    "default": field.default,
                    "options": field.options,
                }
                for field in task.manifest.config_fields
            ],
            result_blocks=[
                {
                    "key": block.key,
                    "label": block.label,
                    "source_key": block.source_key,
                    "description": block.description,
                }
                for block in task.manifest.result_blocks
            ],
        )
        for task in list_task_modules()
    ]


@router.get("/configurations/{task_key}", response_model=TaskConfigurationResponse)
async def get_task_configuration(task_key: str) -> dict:
    return {
        "task_key": task_key,
        "config": sqlite_store.get_task_configuration(task_key),
    }


@router.put("/configurations/{task_key}", response_model=TaskConfigurationResponse)
async def save_task_configuration(task_key: str, payload: TaskConfigurationSaveRequest) -> dict:
    try:
        get_task_module(task_key)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    sqlite_store.save_task_configuration(task_key, payload.config)
    return {
        "task_key": task_key,
        "config": payload.config,
    }


@router.post("/runs", response_model=TaskRunResponse)
async def create_task_run(payload: TaskRunCreateRequest) -> dict:
    try:
        task = get_task_module(payload.task_key)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    active_run = run_store.get_active_run()
    if active_run:
        raise HTTPException(status_code=409, detail="已有任务正在运行，请先停止当前任务。")

    run = run_store.create_run(
        task_key=task.manifest.key,
        task_name=task.manifest.name,
        vendor=payload.vendor,
        concurrency=payload.concurrency,
        config=payload.config,
        item_count=0 if task.dynamic_work_config_key() else task.resolve_item_count(payload.config),
    )
    try:
        await task_control.start(run.id)
    except TaskControlError as exc:
        run_store.mark_run_stopped(run.id, str(exc))
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return run_store.to_dict(run, include_logs=False)


@router.post("/runs/active/stop", response_model=TaskRunResponse)
async def stop_active_task_run() -> dict:
    run_id = await task_control.stop()
    if not run_id:
        raise HTTPException(status_code=404, detail="没有正在运行的任务。")
    return run_store.to_dict(run_store.get_run(run_id), include_logs=False)


@router.post("/runs/{run_id}/stop", response_model=TaskRunResponse)
async def stop_task_run(run_id: str) -> dict:
    try:
        run_store.get_run(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Task run not found.") from exc

    stopped_run_id = await task_control.stop(run_id)
    if not stopped_run_id:
        raise HTTPException(status_code=404, detail="没有正在运行的任务。")
    return run_store.to_dict(run_store.get_run(stopped_run_id), include_logs=False)


@router.get("/runs", response_model=list[TaskRunResponse])
async def list_task_runs() -> list[dict]:
    return [
        run_store.to_dict(run, include_logs=False)
        for run in run_store.list_runs()
    ]


@router.websocket("/runs/ws")
async def stream_task_runs(websocket: WebSocket) -> None:
    await websocket.accept()

    for run in run_store.list_runs():
        await websocket.send_json(run_store.to_dict(run, include_logs=False))

    queue = run_event_hub.subscribe("runs")
    try:
        while True:
            event = await queue.get()
            await websocket.send_json(event)
    except WebSocketDisconnect:
        pass
    finally:
        run_event_hub.unsubscribe("runs", queue)


@router.get("/runs/{run_id}", response_model=TaskRunResponse)
async def get_task_run(run_id: str) -> dict:
    try:
        run = run_store.get_run(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Task run not found.") from exc

    return run_store.to_dict(run, include_logs=False)


@router.get("/runs/{run_id}/logs", response_model=list[TaskRunLogResponse])
async def get_task_run_logs(
    run_id: str,
    limit: int = Query(default=1000, ge=1, le=10000),
) -> list[dict]:
    try:
        logs = run_store.list_logs(run_id, limit=limit)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Task run not found.") from exc

    return [
        {
            "id": log.id,
            "level": log.level,
            "message": log.message,
            "timestamp": log.timestamp,
            "item_id": log.item_id,
            "seq": log.seq,
        }
        for log in logs
    ]


@router.websocket("/runs/{run_id}/logs/ws")
async def stream_task_run_logs(websocket: WebSocket, run_id: str) -> None:
    await websocket.accept()

    try:
        existing_logs = run_store.list_logs(run_id, limit=1000)
    except KeyError:
        await websocket.close(code=4404, reason="Task run not found.")
        return

    for log in existing_logs:
        await websocket.send_json(
            {
                "id": log.id,
                "level": log.level,
                "message": log.message,
                "timestamp": log.timestamp,
                "item_id": log.item_id,
                "seq": log.seq,
            }
        )

    queue = log_event_hub.subscribe(run_id)
    try:
        while True:
            event = await queue.get()
            await websocket.send_json(event)
    except WebSocketDisconnect:
        pass
    finally:
        log_event_hub.unsubscribe(run_id, queue)
