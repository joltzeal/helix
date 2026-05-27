from __future__ import annotations

import asyncio
from typing import Any

from app.services.run_store import run_store
from app.task_modules.base import TaskExecutionContext
from app.task_modules.registry import get_task_module


async def run_task(run_id: str) -> None:
    run = run_store.get_run(run_id)
    task_module = get_task_module(run.task_key)
    work_config_key = task_module.dynamic_work_config_key()

    if run.status in {"stopping", "stopped"}:
        run_store.mark_run_stopped(run.id, "任务已停止，未继续执行。")
        return

    run_store.mark_run_started(run.id)

    async def run_item(item_id: str) -> None:
        item = next(item for item in run_store.get_run(run.id).items if item.id == item_id)
        result_message: str | None = None
        error_message: str | None = None
        cancelled = False

        try:
            run_store.mark_item_started(run.id, item.id)
            result = await task_module.run(
                TaskExecutionContext(
                    run_id=run.id,
                    item_id=item.id,
                    item_index=item.item_index,
                    vendor=run.vendor,
                    config=run.config,
                    log=lambda level, message: run_store.add_log(run.id, level, message, item.id),
                    mark_profile_created=lambda profile_id: run_store.mark_item_profile_created(
                        run.id,
                        item.id,
                        profile_id,
                    ),
                    mark_browser_opened=lambda debug_address, websocket_url, pid, seq: run_store.mark_item_browser_opened(
                        run.id,
                        item.id,
                        debug_address,
                        websocket_url,
                        pid,
                        seq,
                    ),
                    mark_browser_closing=lambda: run_store.mark_item_closing(run.id, item.id),
                    mark_browser_deleting=lambda: run_store.mark_item_deleting(run.id, item.id),
                    list_run_profile_ids=lambda: run_store.list_run_profile_ids(run.id),
                    reserve_config_textarea_line=lambda config_key: run_store.reserve_config_textarea_line(
                        run.id,
                        item.id,
                        config_key,
                    ),
                    update_result_json=lambda result_id, status, message="", extra=None: run_store.update_result_json(
                        run.id,
                        result_id,
                        status,
                        message,
                        extra,
                    ),
                )
            )
            result_message = _result_message(result)
        except asyncio.CancelledError:
            cancelled = True
            raise
        except Exception as exc:
            error_message = str(exc)
        finally:
            if cancelled:
                return
            if error_message:
                run_store.mark_item_failed(run.id, item.id, error_message)
            else:
                run_store.mark_item_completed(
                    run.id,
                    item.id,
                    result_message or "任务项执行完成。",
                )

    async def run_dynamic_worker() -> None:
        assert work_config_key is not None
        while True:
            item = run_store.add_run_item_if_work_available(run.id, work_config_key)
            if item is None:
                return
            await run_item(item.id)

    try:
        if work_config_key:
            await asyncio.gather(*(run_dynamic_worker() for _ in range(run.concurrency)))
        else:
            await asyncio.gather(*(run_item(item.id) for item in list(run.items)))
    except asyncio.CancelledError:
        run_store.mark_run_stopped(run.id, "任务已停止，不再执行后续操作。")
        raise

    if run_store.get_run(run.id).status == "stopping":
        run_store.mark_run_stopped(run.id, "任务已停止，不再执行后续操作。")
    else:
        run_store.mark_run_finished(run.id)


def _result_message(result: dict[str, Any]) -> str:
    message = result.get("message")
    if isinstance(message, str) and message:
        return message
    return "任务项执行完成。"
