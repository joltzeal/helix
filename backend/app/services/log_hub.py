from __future__ import annotations

import asyncio
from threading import RLock
from typing import Any


class EventHub:
    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue[dict[str, Any]]]] = {}
        self._lock = RLock()

    def subscribe(self, run_id: str) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=1000)
        with self._lock:
            self._subscribers.setdefault(run_id, set()).add(queue)
        return queue

    def unsubscribe(self, run_id: str, queue: asyncio.Queue[dict[str, Any]]) -> None:
        with self._lock:
            queues = self._subscribers.get(run_id)
            if not queues:
                return
            queues.discard(queue)
            if not queues:
                self._subscribers.pop(run_id, None)

    def publish(self, run_id: str, event: dict[str, Any]) -> None:
        with self._lock:
            queues = list(self._subscribers.get(run_id, set()))

        for queue in queues:
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            queue.put_nowait(event)


log_event_hub = EventHub()
run_event_hub = EventHub()
