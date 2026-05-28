from __future__ import annotations

from app.task_modules.base import AutomationTaskModule

__all__ = ["get_task_module", "list_task_modules"]


def get_task_module(key: str) -> AutomationTaskModule:
    from .registry import get_task_module as resolve_task_module

    return resolve_task_module(key)


def list_task_modules() -> list[AutomationTaskModule]:
    from .registry import list_task_modules as resolve_task_modules

    return resolve_task_modules()
