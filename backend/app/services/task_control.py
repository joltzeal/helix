from __future__ import annotations

import asyncio

from app.services.browser_sessions import browser_session_service
from app.services.log_store import log_store
from app.services.runtime_store import runtime_store
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
            active_run = runtime_store.get_active_run()
            if active_run and active_run.id != run_id:
                raise TaskControlError("已有任务正在运行，请先停止当前任务。")
            self._run_id = run_id
            self._task = asyncio.create_task(self._run_and_clear(run_id))

    async def stop(self, run_id: str | None = None, *, force_cleanup: bool = False) -> str | None:
        async with self._lock:
            target_run_id = run_id or self._run_id or (runtime_store.get_active_run().id if runtime_store.get_active_run() else None)
            if not target_run_id:
                return None
            runtime_store.request_stop(target_run_id)
            task_to_cancel = self._task if self._run_id == target_run_id else None
            if task_to_cancel and not task_to_cancel.done():
                task_to_cancel.cancel()

        run = runtime_store.get_run(target_run_id)
        await log_store.add(target_run_id, "warn", "已请求停止任务。")
        await browser_session_service.cleanup_run(target_run_id, task_key=run.task_key, force=force_cleanup)

        if task_to_cancel:
            try:
                await asyncio.wait_for(asyncio.shield(task_to_cancel), timeout=10)
            except (asyncio.CancelledError, TimeoutError):
                pass
        runtime_store.cancel_pending_items(target_run_id)
        runtime_store.finish_run(target_run_id)
        return target_run_id

    async def stop_on_shutdown(self) -> None:
        run_id = await self.stop(force_cleanup=True)
        if run_id:
            await log_store.add(run_id, "warn", "后端正在退出，已停止当前任务。")

    async def _run_and_clear(self, run_id: str) -> None:
        try:
            await run_task(run_id)
        finally:
            async with self._lock:
                if self._run_id == run_id:
                    self._run_id = None
                    self._task = None


task_control = TaskControlService()
