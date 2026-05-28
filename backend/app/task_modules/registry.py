from app.task_modules.base import AutomationTaskModule
from app.task_modules.test_email import TestEmailTaskModule
from app.services.plugin_registry import plugin_registry


_TASK_MODULES: dict[str, AutomationTaskModule] = {
    TestEmailTaskModule.manifest.key: TestEmailTaskModule(),
}


def list_task_modules() -> list[AutomationTaskModule]:
    return [*_TASK_MODULES.values(), *plugin_registry.list_modules()]


def get_task_module(key: str) -> AutomationTaskModule:
    try:
        return _TASK_MODULES[key]
    except KeyError:
        pass

    if plugin_registry.has_module(key):
        return plugin_registry.get_module(key)

    raise ValueError(f"Unknown task module: {key}")
