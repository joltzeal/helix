from __future__ import annotations

from threading import RLock
from uuid import uuid4

from app.services.models import BrowserSessionRecord, TaskRunRecord, WorkItemRecord, utc_now
from app.services.runtime_events import runtime_event_hub
from app.task_modules.base import WorkItemSpec


class RuntimeStore:
    def __init__(self) -> None:
        self._runs: dict[str, TaskRunRecord] = {}
        self._sessions: dict[str, BrowserSessionRecord] = {}
        self._lock = RLock()

    def create_run(
        self,
        *,
        task_key: str,
        task_name: str,
        vendor: str,
        concurrency: int,
        config: dict,
        work_items: list[WorkItemSpec],
        cleanup_policy: str,
    ) -> TaskRunRecord:
        run_id = uuid4().hex
        run = TaskRunRecord(
            id=run_id,
            task_key=task_key,
            task_name=task_name,
            vendor=vendor,
            status="pending",
            concurrency=concurrency,
            config=config,
            cleanup_policy=cleanup_policy,
            items=[
                WorkItemRecord(
                    id=uuid4().hex,
                    run_id=run_id,
                    index=index,
                    key=spec.key,
                    label=spec.label,
                    input=spec.input,
                )
                for index, spec in enumerate(work_items, start=1)
            ],
        )
        with self._lock:
            self._runs[run.id] = run
        self.publish_run(run.id)
        return run

    def list_runs(self) -> list[TaskRunRecord]:
        with self._lock:
            return sorted(self._runs.values(), key=lambda run: run.created_at, reverse=True)

    def get_run(self, run_id: str) -> TaskRunRecord:
        with self._lock:
            return self._runs[run_id]

    def get_active_run(self) -> TaskRunRecord | None:
        with self._lock:
            active = [run for run in self._runs.values() if run.status in {"pending", "running", "stopping"}]
            if not active:
                return None
            return sorted(active, key=lambda run: run.created_at, reverse=True)[0]

    def start_run(self, run_id: str) -> None:
        with self._lock:
            run = self._runs[run_id]
            run.status = "running"
            run.started_at = utc_now()
        self.publish_run(run_id)

    def finish_run(self, run_id: str) -> None:
        with self._lock:
            run = self._runs[run_id]
            if run.status == "stopping":
                run.status = "cancelled"
            else:
                failed = any(item.status == "failed" for item in run.items)
                cancelled = any(item.status == "cancelled" for item in run.items)
                run.status = "cancelled" if cancelled else "failed" if failed else "completed"
            run.finished_at = utc_now()
        self.publish_run(run_id)

    def fail_run(self, run_id: str, error: str) -> None:
        with self._lock:
            run = self._runs[run_id]
            run.status = "failed"
            run.error = error
            run.finished_at = utc_now()
        self.publish_run(run_id)

    def request_stop(self, run_id: str) -> None:
        with self._lock:
            run = self._runs[run_id]
            if run.status in {"pending", "running"}:
                run.status = "stopping"
        self.publish_run(run_id)

    def is_stopping(self, run_id: str) -> bool:
        with self._lock:
            return self._runs[run_id].status in {"stopping", "cancelled"}

    def start_item(self, run_id: str, work_item_id: str) -> WorkItemRecord:
        with self._lock:
            item = self._find_item_locked(run_id, work_item_id)
            item.status = "running"
            item.started_at = utc_now()
            item.message = "任务项开始运行。"
        self.publish_run(run_id)
        return item

    def complete_item(self, run_id: str, work_item_id: str, message: str = "") -> None:
        with self._lock:
            item = self._find_item_locked(run_id, work_item_id)
            item.status = "completed"
            item.message = message
            item.finished_at = utc_now()
        self.publish_run(run_id)

    def fail_item(self, run_id: str, work_item_id: str, error: str) -> None:
        with self._lock:
            item = self._find_item_locked(run_id, work_item_id)
            item.status = "failed"
            item.error = error
            item.finished_at = utc_now()
        self.publish_run(run_id)

    def cancel_pending_items(self, run_id: str, message: str = "任务已取消。") -> None:
        with self._lock:
            run = self._runs[run_id]
            for item in run.items:
                if item.status in {"pending", "running"}:
                    item.status = "cancelled"
                    item.message = message
                    item.finished_at = utc_now()
        self.publish_run(run_id)

    def add_session(self, session: BrowserSessionRecord) -> None:
        with self._lock:
            self._sessions[session.id] = session
        self.publish_session(session.run_id, session.id)

    def get_session(self, session_id: str) -> BrowserSessionRecord:
        with self._lock:
            return self._sessions[session_id]

    def list_run_sessions(self, run_id: str) -> list[BrowserSessionRecord]:
        with self._lock:
            return [
                session
                for session in sorted(self._sessions.values(), key=lambda current: current.created_at)
                if session.run_id == run_id
            ]

    def update_session(self, session_id: str, **changes: object) -> BrowserSessionRecord:
        with self._lock:
            session = self._sessions[session_id]
            for key, value in changes.items():
                if hasattr(session, key):
                    setattr(session, key, value)
        self.publish_session(session.run_id, session.id)
        return session

    def publish_run(self, run_id: str) -> None:
        run = self.get_run(run_id)
        runtime_event_hub.publish("runs", run.to_dict())
        runtime_event_hub.publish(f"run:{run_id}", run.to_dict())

    def publish_session(self, run_id: str, session_id: str) -> None:
        session = self.get_session(session_id)
        runtime_event_hub.publish("browser_sessions", session.to_dict())
        runtime_event_hub.publish(f"run:{run_id}:browser_sessions", session.to_dict())

    def _find_item_locked(self, run_id: str, work_item_id: str) -> WorkItemRecord:
        run = self._runs[run_id]
        return next(item for item in run.items if item.id == work_item_id)


runtime_store = RuntimeStore()
