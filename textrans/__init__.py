"""TexTrans — 干净的 LaTeX 论文翻译内核。

核心思想(算法层面借鉴 gpt_academic,clean-room 重写):
  二值掩码 (mask) → 链表 (linkedlist) → 顺序合并 (merge) → 编译日志回退 (compile)

替代旧的「编号回填」策略,从根本上消除对齐崩坏与命令粘连。
"""
from __future__ import annotations

__version__ = "0.1.0"

from .types import (
    PRESERVE,
    TRANSFORM,
    ProgressEvent,
    SegmentStats,
    Stage,
    TranslateConfig,
)

__all__ = [
    "PRESERVE",
    "TRANSFORM",
    "ProgressEvent",
    "SegmentStats",
    "Stage",
    "TranslateConfig",
    "__version__",
]
