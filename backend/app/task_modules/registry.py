from importlib import import_module
from inspect import isclass
from pathlib import Path

from app.task_modules.base import AutomationTaskModule
from app.task_modules.test_email import TestEmailTaskModule
from app.core.config import get_settings
from app.services.plugin_registry import plugin_registry


_TASK_MODULES: dict[str, AutomationTaskModule] = {
    TestEmailTaskModule.manifest.key: TestEmailTaskModule(),
}


def list_task_modules() -> list[AutomationTaskModule]:
    return [*_active_task_modules().values(), *plugin_registry.list_modules()]


def get_task_module(key: str) -> AutomationTaskModule:
    task_modules = _active_task_modules()
    try:
        return task_modules[key]
    except KeyError:
        pass

    if plugin_registry.has_module(key):
        return plugin_registry.get_module(key)

    raise ValueError(f"Unknown task module: {key}")


def _active_task_modules() -> dict[str, AutomationTaskModule]:
    modules = dict(_TASK_MODULES)
    if get_settings().mode == "development":
        modules.update(_load_development_task_modules())
    return modules


def _load_development_task_modules() -> dict[str, AutomationTaskModule]:
    modules: dict[str, AutomationTaskModule] = {}
    task_modules_dir = Path(__file__).resolve().parent

    for package_dir in sorted(path for path in task_modules_dir.iterdir() if path.is_dir()):
        if package_dir.name.startswith("_") or package_dir.name == "__pycache__":
            continue
        if not (package_dir / "__init__.py").exists():
            continue

        for module in _candidate_modules(package_dir.name):
            for task_class in _iter_task_module_classes(module):
                task = task_class()
                modules[task.manifest.key] = task

    return modules


def _candidate_modules(package_name: str):
    for import_name in (
        f"app.task_modules.{package_name}",
        f"app.task_modules.{package_name}.module",
    ):
        try:
            yield import_module(import_name)
        except ModuleNotFoundError as exc:
            if exc.name != import_name:
                raise


def _iter_task_module_classes(module):
    for value in module.__dict__.values():
        if (
            isclass(value)
            and issubclass(value, AutomationTaskModule)
            and value is not AutomationTaskModule
            and getattr(value, "manifest", None) is not None
        ):
            yield value
