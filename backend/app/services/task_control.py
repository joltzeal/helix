from __future__ import annotations

import asyncio

from app.services.run_store import run_store
from app.services.task_runner import run_task


class TaskControlError(RuntimeError):
    pass


class TaskControlService:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._task: asyncio.Task[None] | None = None
        self._run_id: str | None = None

    async def start(self, run_id: str) -> None:
        async with self._lock:
            if self._task and not self._task.done():
                raise TaskControlError("已有任务正在运行，请先停止当前任务。")

            active_run = run_store.get_active_run()
            if active_run and active_run.id != run_id:
                raise TaskControlError("已有任务正在运行，请先停止当前任务。")

            self._run_id = run_id
            self._task = asyncio.create_task(self._run_and_clear(run_id))

    async def stop(self, run_id: str | None = None) -> str | None:
        async with self._lock:
            target_run_id = run_id or self._run_id or run_store.get_active_run_id()
            if not target_run_id:
                return None

            run_store.mark_run_stopping(target_run_id)

            if self._task and not self._task.done() and self._run_id == target_run_id:
                self._task.cancel()
            else:
                run_store.mark_run_stopped(target_run_id, "任务已停止。")

            return target_run_id

    async def _run_and_clear(self, run_id: str) -> None:
        try:
            await run_task(run_id)
        finally:
            async with self._lock:
                if self._run_id == run_id:
                    self._run_id = None
                    self._task = None


task_control = TaskControlService()
