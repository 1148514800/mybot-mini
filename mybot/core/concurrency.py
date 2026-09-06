from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any


class SessionExecutionCoordinator:
    """Serialize work per session while bounding cross-session concurrency."""

    def __init__(self, max_concurrent_sessions: int = 4) -> None:
        if isinstance(max_concurrent_sessions, bool) or not 1 <= max_concurrent_sessions <= 32:
            raise ValueError("max_concurrent_sessions must be an integer from 1 to 32")
        self.max_concurrent_sessions = max_concurrent_sessions
        self._semaphore = asyncio.Semaphore(max_concurrent_sessions)
        self._locks: dict[str, asyncio.Lock] = {}
        self._guard = asyncio.Lock()
        self._closed = False
        self._tasks: set[asyncio.Task[Any]] = set()

    async def _session_lock(self, session_key: str) -> asyncio.Lock:
        async with self._guard:
            return self._locks.setdefault(session_key, asyncio.Lock())

    async def execute(
        self,
        session_key: str,
        operation: Callable[[], Awaitable[Any]],
    ) -> Any:
        if self._closed:
            raise RuntimeError("session execution coordinator is stopped")
        lock = await self._session_lock(session_key)
        async with lock:
            async with self._semaphore:
                return await operation()

    def track(self, task: asyncio.Task[Any]) -> None:
        self._tasks.add(task)
        task.add_done_callback(self._task_done)

    def _task_done(self, task: asyncio.Task[Any]) -> None:
        self._tasks.discard(task)
        if task.cancelled():
            return
        try:
            task.result()
        except BaseException as exc:
            asyncio.get_running_loop().call_exception_handler(
                {
                    "message": "session execution task failed",
                    "exception": exc,
                    "task": task,
                }
            )

    async def shutdown(self) -> None:
        self._closed = True
        tasks = list(self._tasks)
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()
