from __future__ import annotations

import asyncio

from app.fingerprint_browsers.factory import create_fingerprint_browser_client
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
        task_to_cancel: asyncio.Task[None] | None = None
        async with self._lock:
            target_run_id = run_id or self._run_id or run_store.get_active_run_id()
            if not target_run_id:
                return None

            run_store.mark_run_stopping(target_run_id)

            if self._task and not self._task.done() and self._run_id == target_run_id:
                task_to_cancel = self._task
                task_to_cancel.cancel()
            else:
                run_store.mark_run_stopped(target_run_id, "任务已停止。")

        await self._cleanup_run_profiles(target_run_id)

        if task_to_cancel:
            try:
                await asyncio.wait_for(asyncio.shield(task_to_cancel), timeout=10)
            except asyncio.CancelledError:
                pass
            except TimeoutError:
                run_store.add_log(target_run_id, "warn", "任务取消仍在等待后台调用返回，已清理浏览器并阻止后续操作。")

        return target_run_id

    async def stop_on_shutdown(self) -> None:
        run_id = await self.stop()
        if run_id:
            run_store.add_log(run_id, "warn", "后端正在退出，已停止当前任务。")

    async def _run_and_clear(self, run_id: str) -> None:
        try:
            await run_task(run_id)
        finally:
            async with self._lock:
                if self._run_id == run_id:
                    self._run_id = None
                    self._task = None

    async def _cleanup_run_profiles(self, run_id: str) -> None:
        profile_ids = run_store.list_active_profile_ids(run_id)
        if not profile_ids:
            return

        try:
            run = run_store.get_run(run_id)
            client = create_fingerprint_browser_client(run.vendor)
        except Exception as exc:
            run_store.add_log(run_id, "warn", f"停止任务时无法创建浏览器客户端：{exc}")
            return

        for profile_id in profile_ids:
            try:
                await client.stop_profile(profile_id)
                run_store.add_log(run_id, "debug", f"已请求关闭浏览器窗口：{profile_id}")
            except Exception as exc:
                run_store.add_log(run_id, "warn", f"关闭浏览器窗口失败：{profile_id}，原因：{exc}")

            try:
                await client.delete_profile(profile_id)
                run_store.add_log(run_id, "debug", f"已请求删除浏览器窗口：{profile_id}")
            except Exception as exc:
                run_store.add_log(run_id, "warn", f"删除浏览器窗口失败：{profile_id}，原因：{exc}")


task_control = TaskControlService()
