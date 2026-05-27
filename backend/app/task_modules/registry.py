from app.task_modules.base import AutomationTaskModule
from app.task_modules.test_email import TestEmailTaskModule
from app.task_modules.uber import UberTaskModule


_TASK_MODULES: dict[str, AutomationTaskModule] = {
    UberTaskModule.manifest.key: UberTaskModule(),
    TestEmailTaskModule.manifest.key: TestEmailTaskModule(),
}


def list_task_modules() -> list[AutomationTaskModule]:
    return list(_TASK_MODULES.values())


def get_task_module(key: str) -> AutomationTaskModule:
    try:
        return _TASK_MODULES[key]
    except KeyError as exc:
        raise ValueError(f"Unknown task module: {key}") from exc
