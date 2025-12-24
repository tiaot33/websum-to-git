from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

RunFunc = Callable[[], Any]
AsyncHandler = Callable[..., Awaitable[None]]


class TaskQueueFullError(RuntimeError):
    pass


class ChatTaskQueueFullError(RuntimeError):
    pass


@dataclass(frozen=True)
class QueueStatus:
    max_concurrent_jobs: int
    max_queue_size: int
    max_queue_size_per_chat: int
    global_pending: int
    global_running: int
    chat_pending: int
    chat_running: int


@dataclass
class Job:
    job_id: str
    chat_id: int
    status_message_id: int
    created_at: datetime
    kind: str
    run: RunFunc
    on_start: AsyncHandler | None = None
    on_success: AsyncHandler | None = None
    on_failure: AsyncHandler | None = None


@dataclass
class _ChatState:
    queue: asyncio.Queue[Job]
    worker: asyncio.Task[None] | None = None
    pending: int = 0
    running: int = 0


class TaskScheduler:
    """Telegram Bot 任务调度器（in-memory）。

    设计约束：
    - KISS：只做入队、限流、顺序与回调，不引入外部队列依赖。
    - YAGNI：不做持久化、不做 running 任务强制取消。
    - DRY：统一封装线程池与并发控制，避免在 handler 里重复样板。
    """

    def __init__(
        self,
        *,
        max_concurrent_jobs: int,
        max_queue_size: int,
        max_queue_size_per_chat: int,
    ) -> None:
        if max_concurrent_jobs <= 0:
            raise ValueError("max_concurrent_jobs 必须 > 0")
        if max_queue_size <= 0:
            raise ValueError("max_queue_size 必须 > 0")
        if max_queue_size_per_chat <= 0:
            raise ValueError("max_queue_size_per_chat 必须 > 0")

        self._max_concurrent_jobs = max_concurrent_jobs
        self._max_queue_size = max_queue_size
        self._max_queue_size_per_chat = max_queue_size_per_chat

        self._semaphore = asyncio.Semaphore(max_concurrent_jobs)
        self._executor = ThreadPoolExecutor(max_workers=max_concurrent_jobs, thread_name_prefix="websum-job")
        self._lock = asyncio.Lock()

        self._chats: dict[int, _ChatState] = {}
        self._global_pending = 0
        self._global_running = 0
        self._closed = False

    async def get_status(self, chat_id: int) -> QueueStatus:
        async with self._lock:
            chat_state = self._chats.get(chat_id)
            return QueueStatus(
                max_concurrent_jobs=self._max_concurrent_jobs,
                max_queue_size=self._max_queue_size,
                max_queue_size_per_chat=self._max_queue_size_per_chat,
                global_pending=self._global_pending,
                global_running=self._global_running,
                chat_pending=chat_state.pending if chat_state else 0,
                chat_running=chat_state.running if chat_state else 0,
            )

    async def enqueue(self, job: Job) -> int:
        """入队任务，返回该 Chat 的 pending 数（含本次）。"""

        if self._closed:
            raise RuntimeError("TaskScheduler 已关闭")

        async with self._lock:
            if self._global_pending >= self._max_queue_size:
                raise TaskQueueFullError("全局队列已满")

            state = self._chats.get(job.chat_id)
            if state is None:
                state = _ChatState(queue=asyncio.Queue())
                self._chats[job.chat_id] = state

            if state.pending >= self._max_queue_size_per_chat:
                raise ChatTaskQueueFullError("会话队列已满")

            state.pending += 1
            self._global_pending += 1
            state.queue.put_nowait(job)

            if state.worker is None or state.worker.done():
                state.worker = asyncio.create_task(self._chat_worker(job.chat_id), name=f"chat-worker:{job.chat_id}")

            return state.pending

    async def shutdown(self) -> None:
        """尽力关闭调度器：取消 worker 并关闭线程池。"""

        async with self._lock:
            if self._closed:
                return
            self._closed = True
            workers = [state.worker for state in self._chats.values() if state.worker]
            self._chats.clear()

        for t in workers:
            t.cancel()
        if workers:
            await asyncio.gather(*workers, return_exceptions=True)

        self._executor.shutdown(wait=False, cancel_futures=True)

    async def _chat_worker(self, chat_id: int) -> None:
        while True:
            async with self._lock:
                state = self._chats.get(chat_id)
                if state is None:
                    return

            job = await state.queue.get()

            async with self._semaphore:
                async with self._lock:
                    # pending -> running（pending 统计“未开始”的任务，包含等待资源的任务）
                    state.pending = max(state.pending - 1, 0)
                    self._global_pending = max(self._global_pending - 1, 0)
                    state.running = 1
                    self._global_running += 1

                try:
                    if job.on_start:
                        await job.on_start()

                    loop = asyncio.get_running_loop()
                    result = await loop.run_in_executor(self._executor, job.run)

                    if job.on_success:
                        await job.on_success(result)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:  # noqa: BLE001
                    logger.exception("任务执行失败: chat=%s job=%s kind=%s", job.chat_id, job.job_id, job.kind)
                    try:
                        if job.on_failure:
                            await job.on_failure(exc)
                    except Exception:  # noqa: BLE001
                        logger.exception("失败回调执行失败: chat=%s job=%s", job.chat_id, job.job_id)
                finally:
                    async with self._lock:
                        state.running = 0
                        self._global_running = max(self._global_running - 1, 0)

            state.queue.task_done()

            # 任务耗尽时清理 chat state，避免长时间堆积 idle worker
            async with self._lock:
                state = self._chats.get(chat_id)
                if state and state.queue.empty() and state.pending == 0 and state.running == 0:
                    # 只有当前 worker 才能清理自己，避免误删新 worker
                    if state.worker is asyncio.current_task():
                        del self._chats[chat_id]
                    return
