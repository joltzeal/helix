from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.schemas.tasks import PluginModuleResponse
from app.services.plugin_registry import PluginError, PluginRecord, plugin_registry

router = APIRouter(prefix="/api/task-modules", tags=["task-modules"])


@router.get("", response_model=list[PluginModuleResponse])
async def list_plugin_modules() -> list[dict]:
    return [_plugin_record_to_dict(record) for record in plugin_registry.list_records()]


@router.post("/upload", response_model=PluginModuleResponse)
async def upload_plugin_module(file: UploadFile = File(...)) -> dict:
    if not file.filename or not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="请上传 .zip 插件包。")

    suffix = Path(file.filename).suffix or ".zip"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temporary:
        temporary_path = Path(temporary.name)
        while chunk := await file.read(1024 * 1024):
            temporary.write(chunk)

    try:
        record = plugin_registry.install_zip(temporary_path)
    except PluginError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        temporary_path.unlink(missing_ok=True)

    return _plugin_record_to_dict(record)


@router.post("/{key}/reload", response_model=PluginModuleResponse)
async def reload_plugin_module(key: str) -> dict:
    try:
        record = plugin_registry.reload(key)
    except PluginError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _plugin_record_to_dict(record)


@router.delete("/{key}", response_model=list[PluginModuleResponse])
async def delete_plugin_module(key: str) -> list[dict]:
    try:
        plugin_registry.delete(key)
    except PluginError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return [_plugin_record_to_dict(record) for record in plugin_registry.list_records()]


@router.post("/reload", response_model=list[PluginModuleResponse])
async def reload_all_plugin_modules() -> list[dict]:
    return [_plugin_record_to_dict(record) for record in plugin_registry.reload_all()]


def _plugin_record_to_dict(record: PluginRecord) -> dict:
    return {
        "key": record.key,
        "name": record.name,
        "version": record.version,
        "description": record.description,
        "entry": record.entry,
        "status": record.status,
        "error": record.error,
    }
