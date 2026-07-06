"""TexTrans 核心数据类型。

clean-room 实现,不复制 gpt_academic (GPL v3) 的任何代码。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Optional


# 掩码取值:与原文等长的 uint8 数组中,每个字符标记为保护或翻译。
PRESERVE = 0  # 保护:不发给 LLM,原样保留(公式、命令、引用等)
TRANSFORM = 1  # 翻译:发给 LLM


class Stage(str, Enum):
    """翻译流水线阶段。"""

    QUEUED = "queued"
    DOWNLOADING = "downloading"
    SPLITTING = "splitting"
    TRANSLATING = "translating"
    MERGING = "merging"
    COMPILING = "compiling"
    BILINGUAL = "bilingual"
    DONE = "done"
    FAILED = "failed"


@dataclass
class ProgressEvent:
    """进度事件,通过回调上报给 CLI / 后端。"""

    stage: Stage
    message: str = ""
    current: int = 0
    total: int = 0

    @property
    def fraction(self) -> float:
        return (self.current / self.total) if self.total else 0.0


# 进度回调签名
ProgressCallback = Callable[[ProgressEvent], None]


@dataclass
class TranslateConfig:
    """一次翻译任务的运行参数。"""

    provider: str = "kimi"
    max_workers: int = 8
    max_token_per_segment: int = 1024
    max_compile_retries: int = 32
    target_lang: str = "简体中文"
    make_bilingual: bool = True
    add_watermark: bool = False
    watermark_path: Optional[Path] = None
    use_cache: bool = True


@dataclass
class SegmentStats:
    """翻译产出的统计,用于验证与报告。"""

    total_segments: int = 0
    translated_segments: int = 0
    preserved_segments: int = 0
    reverted_on_compile: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    api_calls: int = 0
    warnings: list[str] = field(default_factory=list)
