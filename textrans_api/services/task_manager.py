"""任务管理器:后台执行翻译流水线,跟踪状态,向 WS 订阅者推送进度。

- 每个任务在 ThreadPoolExecutor 里跑 Pipeline(阻塞型:latex/网络/LLM)。
- Pipeline 的 on_progress 回调(在 worker 线程)把事件塞进 asyncio.Queue,
  用 loop.call_soon_threadsafe 跨线程安全投递给事件循环。
- WS 端点订阅该队列,实时收到进度。
"""
from __future__ import annotations

import asyncio
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from textrans.config import load_config
from textrans.core.pipeline import Pipeline
from textrans.types import ProgressEvent, Stage, TranslateConfig

from .db import TaskStore


@dataclass
class TaskState:
    task_id: str
    status: str = "queued"  # queued | running | done | failed
    stage: str = Stage.QUEUED.value
    message: str = ""
    current: int = 0
    total: int = 0
    error: Optional[str] = None
    translated_pdf: Optional[Path] = None
    bilingual_pdf: Optional[Path] = None
    original_pdf: Optional[Path] = None
    workdir: Optional[Path] = None
    title: Optional[str] = None
    source: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    # WS 订阅者队列(可能多个客户端看同一任务)
    subscribers: List[asyncio.Queue] = field(default_factory=list)

    def to_json(self) -> dict:
        """序列化为可持久化的 dict(排除运行时的 asyncio 队列)。"""
        def _p(x: Optional[Path]) -> Optional[str]:
            return str(x) if x else None
        return {
            "task_id": self.task_id,
            "status": self.status,
            "stage": self.stage,
            "message": self.message,
            "current": self.current,
            "total": self.total,
            "error": self.error,
            "translated_pdf": _p(self.translated_pdf),
            "bilingual_pdf": _p(self.bilingual_pdf),
            "original_pdf": _p(self.original_pdf),
            "workdir": _p(self.workdir),
            "title": self.title,
            "source": self.source,
            "created_at": self.created_at,
        }

    @classmethod
    def from_json(cls, d: dict) -> "TaskState":
        def _p(v) -> Optional[Path]:
            return Path(v) if v else None
        return cls(
            task_id=d["task_id"],
            status=d.get("status", "done"),
            stage=d.get("stage", Stage.DONE.value),
            message=d.get("message", ""),
            current=d.get("current", 0),
            total=d.get("total", 0),
            error=d.get("error"),
            translated_pdf=_p(d.get("translated_pdf")),
            bilingual_pdf=_p(d.get("bilingual_pdf")),
            original_pdf=_p(d.get("original_pdf")),
            workdir=_p(d.get("workdir")),
            title=d.get("title"),
            source=d.get("source"),
            created_at=d.get("created_at", time.time()),
        )


class TaskManager:
    def __init__(self, max_concurrent: int = 2):
        self._tasks: Dict[str, TaskState] = {}
        self._executor = ThreadPoolExecutor(max_workers=max_concurrent)
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._config = load_config()
        # SQLite 持久化:重启不丢历史。数据库放 workdir/textrans.db。
        self._store = TaskStore(self._config.workdir / "textrans.db")
        self._store.mark_interrupted()
        self._load()

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    # -------------------------------------------------------------- #
    def _load(self) -> None:
        """启动时从数据库恢复历史任务到内存。"""
        for row in self._store.all():
            state = TaskState.from_json(row)
            self._tasks[state.task_id] = state

    def _save(self, state: TaskState) -> None:
        """把单个任务快照写回数据库(upsert)。"""
        try:
            self._store.upsert(state.to_json())
        except Exception:  # noqa: BLE001 - 持久化失败不应影响主流程
            pass

    # -------------------------------------------------------------- #
    def create_task(self, source: str, *, provider: Optional[str] = None,
                    make_bilingual: bool = True, workers: int = 8) -> str:
        task_id = uuid.uuid4().hex[:12]
        state = TaskState(task_id=task_id, source=source)
        self._tasks[task_id] = state
        self._save(state)
        self._executor.submit(self._run, task_id, source, provider, make_bilingual, workers)
        return task_id

    def get(self, task_id: str) -> Optional[TaskState]:
        return self._tasks.get(task_id)

    def all(self) -> List[TaskState]:
        return list(self._tasks.values())

    def subscribe(self, task_id: str) -> Optional[asyncio.Queue]:
        state = self._tasks.get(task_id)
        if state is None:
            return None
        q: asyncio.Queue = asyncio.Queue()
        state.subscribers.append(q)
        return q

    def unsubscribe(self, task_id: str, q: asyncio.Queue) -> None:
        state = self._tasks.get(task_id)
        if state and q in state.subscribers:
            state.subscribers.remove(q)

    # -------------------------------------------------------------- #
    def _push(self, state: TaskState) -> None:
        """把当前状态快照推给所有订阅者(线程安全)。"""
        snapshot = {
            "task_id": state.task_id,
            "status": state.status,
            "stage": state.stage,
            "message": state.message,
            "current": state.current,
            "total": state.total,
            "error": state.error,
        }
        if self._loop is None:
            return
        for q in list(state.subscribers):
            self._loop.call_soon_threadsafe(q.put_nowait, snapshot)

    def _run(self, task_id: str, source: str, provider: Optional[str],
             make_bilingual: bool, workers: int) -> None:
        """在 worker 线程执行流水线。"""
        state = self._tasks[task_id]
        state.status = "running"
        self._save(state)

        def on_progress(ev: ProgressEvent) -> None:
            state.stage = ev.stage.value
            state.message = ev.message
            state.current = ev.current
            state.total = ev.total
            self._push(state)

        try:
            tconf = TranslateConfig(
                provider=provider or self._config.default_provider,
                max_workers=workers,
                make_bilingual=make_bilingual,
                add_watermark=self._config.watermark_path.exists(),
                watermark_path=self._config.watermark_path,
            )
            pipeline = Pipeline(tconf=tconf, config=self._config, on_progress=on_progress)
            result = pipeline.run(source)

            state.workdir = result.workdir
            if result.ok:
                state.status = "done"
                state.stage = Stage.DONE.value
                state.translated_pdf = result.translated_pdf
                state.bilingual_pdf = result.bilingual_pdf
                state.original_pdf = result.original_pdf
                state.title = result.title
                state.message = "完成"
            else:
                state.status = "failed"
                state.stage = Stage.FAILED.value
                state.error = result.message
        except Exception as e:  # noqa: BLE001
            state.status = "failed"
            state.stage = Stage.FAILED.value
            state.error = str(e)
        finally:
            self._save(state)
            self._push(state)
            # 通知订阅者结束
            if self._loop is not None:
                for q in list(state.subscribers):
                    self._loop.call_soon_threadsafe(q.put_nowait, {"_end": True})


# 单例
task_manager = TaskManager()
