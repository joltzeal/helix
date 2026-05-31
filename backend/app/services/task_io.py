from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from app.core.paths import get_data_dir
from app.services.log_store import get_artifacts_dir
from app.services.models import TaskArtifactRecord, TaskResultRecord
from app.services.sqlite_store import sqlite_store


class ResultWriter:
    def __init__(self, *, task_key: str, run_id: str, work_item_id: str) -> None:
        self.task_key = task_key
        self.run_id = run_id
        self.work_item_id = work_item_id

    async def add(
        self,
        key: str,
        data: dict,
        *,
        status: str = "completed",
        message: str = "",
    ) -> str:
        result = TaskResultRecord(
            id=uuid4().hex,
            run_id=self.run_id,
            work_item_id=self.work_item_id,
            key=key,
            status=status,
            data=data,
            message=message,
        )
        sqlite_store.add_task_result(self.task_key, result)
        return result.id


class ArtifactWriter:
    def __init__(self, *, task_key: str, run_id: str, work_item_id: str) -> None:
        self.task_key = task_key
        self.run_id = run_id
        self.work_item_id = work_item_id

    async def save_bytes(
        self,
        key: str,
        filename: str,
        content: bytes,
        *,
        kind: str = "file",
        mime_type: str = "application/octet-stream",
        name: str = "",
    ) -> str:
        safe_filename = _safe_filename(filename)
        path = get_artifacts_dir(self.run_id, self.work_item_id) / safe_filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return self._record(
            key=key,
            kind=kind,
            name=name or safe_filename,
            filename=safe_filename,
            mime_type=mime_type,
            path=path,
            size_bytes=len(content),
        )

    async def save_text(
        self,
        key: str,
        filename: str,
        content: str,
        *,
        kind: str = "text",
        mime_type: str = "text/plain",
        name: str = "",
    ) -> str:
        return await self.save_bytes(
            key,
            filename,
            content.encode("utf-8"),
            kind=kind,
            mime_type=mime_type,
            name=name,
        )

    def _record(
        self,
        *,
        key: str,
        kind: str,
        name: str,
        filename: str,
        mime_type: str,
        path: Path,
        size_bytes: int,
    ) -> str:
        artifact = TaskArtifactRecord(
            id=uuid4().hex,
            run_id=self.run_id,
            work_item_id=self.work_item_id,
            key=key,
            kind=kind,
            name=name,
            filename=filename,
            mime_type=mime_type,
            relative_path=str(path.relative_to(get_data_dir())),
            size_bytes=size_bytes,
        )
        sqlite_store.add_task_artifact(self.task_key, artifact)
        return artifact.id


def _safe_filename(filename: str) -> str:
    cleaned = "".join(char for char in filename if char.isalnum() or char in {".", "-", "_"})
    return cleaned or f"artifact-{uuid4().hex}"
