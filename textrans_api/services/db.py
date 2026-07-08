"""任务持久化:SQLite 单文件数据库。

替代早期的 tasks.json 全量读写。选 SQLite 的理由:
  - Python 标准库自带(零新依赖),单文件,无需起服务;
  - 支持真正的按列查询/排序,重启绝不丢历史;
  - upsert 单条即可,无需每次重写整份数据。

列直接对应 TaskState.to_json() 的键,读写时复用其序列化逻辑。
连接以 check_same_thread=False 打开(任务在 ThreadPoolExecutor 线程写,
FastAPI 事件循环线程读),用一把锁串行化所有访问,保证线程安全。
"""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Dict, List

# TaskState.to_json() 的键顺序即列顺序(task_id 为主键)
_COLUMNS = [
    "task_id", "status", "stage", "message", "current", "total", "error",
    "translated_pdf", "bilingual_pdf", "original_pdf", "workdir",
    "title", "source", "created_at",
]


class TaskStore:
    """线程安全的任务表存储。"""

    def __init__(self, db_path: Path):
        self._path = db_path
        self._lock = threading.Lock()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        cols = ",\n  ".join(
            f"{c} TEXT" if c not in ("current", "total", "created_at")
            else (f"{c} REAL" if c == "created_at" else f"{c} INTEGER")
            for c in _COLUMNS
        )
        with self._lock:
            self._conn.execute(
                f"CREATE TABLE IF NOT EXISTS tasks (\n  {cols},\n  PRIMARY KEY (task_id)\n)"
            )
            self._conn.commit()

    def upsert(self, row: Dict) -> None:
        """插入或更新单条任务(按 task_id)。row 为 TaskState.to_json()。"""
        vals = [row.get(c) for c in _COLUMNS]
        placeholders = ", ".join("?" for _ in _COLUMNS)
        col_list = ", ".join(_COLUMNS)
        updates = ", ".join(f"{c}=excluded.{c}" for c in _COLUMNS if c != "task_id")
        with self._lock:
            self._conn.execute(
                f"INSERT INTO tasks ({col_list}) VALUES ({placeholders}) "
                f"ON CONFLICT(task_id) DO UPDATE SET {updates}",
                vals,
            )
            self._conn.commit()

    def all(self) -> List[Dict]:
        """返回所有任务(dict 列表),按 created_at 倒序。"""
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM tasks ORDER BY created_at DESC"
            )
            return [dict(r) for r in cur.fetchall()]

    def get(self, task_id: str) -> Dict | None:
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
            )
            r = cur.fetchone()
            return dict(r) if r else None

    def mark_interrupted(self) -> None:
        """启动时把上次遗留的 running/queued 标记为失败(进程重启无法续跑)。"""
        with self._lock:
            self._conn.execute(
                "UPDATE tasks SET status='failed', stage='failed', "
                "error='服务重启,任务中断' WHERE status IN ('running','queued')"
            )
            self._conn.commit()
