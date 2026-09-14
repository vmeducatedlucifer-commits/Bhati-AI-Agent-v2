"""Work-stealing scheduler that keeps a very large swarm productive.

Design notes for scale (target: 1200 concurrent agents)
------------------------------------------------------
- Agents are coroutines, not processes: 1200 idle-ish coroutines cost ~MBs, not GBs.
- The real limit is *LLM concurrency*, so an inner semaphore caps in-flight model
  calls (`llm_concurrency`) while the outer pool caps live agents (`max_agents`).
- Work is pulled, not pushed: any free worker steals the next ready task, so a
  slow task never blocks the rest of the swarm.
- Backpressure: the task queue is bounded; producers await instead of exploding memory.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from app.core.logging import get_logger

log = get_logger("swarm.scheduler")


@dataclass(order=True)
class WorkItem:
    priority: int
    sequence: int
    payload: Any = field(compare=False)


@dataclass(slots=True)
class SchedulerStats:
    submitted: int = 0
    completed: int = 0
    failed: int = 0
    in_flight: int = 0
    peak_in_flight: int = 0
    started_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        elapsed = max(0.001, time.time() - self.started_at)
        return {
            "submitted": self.submitted,
            "completed": self.completed,
            "failed": self.failed,
            "in_flight": self.in_flight,
            "peak_in_flight": self.peak_in_flight,
            "throughput_per_min": round(self.completed / elapsed * 60, 2),
            "elapsed_seconds": round(elapsed, 1),
        }


class SwarmScheduler:
    """Bounded, priority-aware, work-stealing pool of agent coroutines."""

    def __init__(
        self,
        max_agents: int = 64,
        llm_concurrency: int = 16,
        queue_size: int = 10_000,
    ) -> None:
        self.max_agents = max_agents
        self.queue: asyncio.PriorityQueue[WorkItem] = asyncio.PriorityQueue(maxsize=queue_size)
        self.llm_semaphore = asyncio.Semaphore(llm_concurrency)
        self.stats = SchedulerStats()
        self._workers: list[asyncio.Task] = []
        self._sequence = 0
        self._running = False
        self._results: list[Any] = []

    # ------------------------------------------------------------- lifecycle
    async def start(self, handler: Callable[[Any], Awaitable[Any]]) -> None:
        if self._running:
            return
        self._running = True
        self._workers = [
            asyncio.create_task(self._worker(index, handler)) for index in range(self.max_agents)
        ]
        log.info("swarm_scheduler_started", workers=self.max_agents)

    async def stop(self) -> None:
        self._running = False
        for worker in self._workers:
            worker.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()

    async def drain(self) -> list[Any]:
        """Wait until every queued item has been processed."""
        await self.queue.join()
        return self._results

    # --------------------------------------------------------------- queueing
    async def submit(self, payload: Any, priority: int = 5) -> None:
        self._sequence += 1
        self.stats.submitted += 1
        await self.queue.put(WorkItem(priority=priority, sequence=self._sequence, payload=payload))

    def pending(self) -> int:
        return self.queue.qsize()

    # ---------------------------------------------------------------- worker
    async def _worker(self, index: int, handler: Callable[[Any], Awaitable[Any]]) -> None:
        while self._running:
            try:
                item = await self.queue.get()
            except asyncio.CancelledError:
                return
            self.stats.in_flight += 1
            self.stats.peak_in_flight = max(self.stats.peak_in_flight, self.stats.in_flight)
            try:
                async with self.llm_semaphore:
                    result = await handler(item.payload)
                self._results.append(result)
                self.stats.completed += 1
            except asyncio.CancelledError:
                self.stats.in_flight -= 1
                self.queue.task_done()
                return
            except Exception as exc:
                self.stats.failed += 1
                log.warning("swarm_task_failed", worker=index, error=str(exc))
            finally:
                self.stats.in_flight -= 1
                self.queue.task_done()
