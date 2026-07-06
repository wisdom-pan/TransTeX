"""LLMProvider 抽象:多模型翻译的统一接口。

- translate_segments 用线程池并发翻译多段,结果按输入顺序返回(future 顺序对齐)。
- 内置令牌桶限速 + 指数退避重试。
- 具体 provider(kimi/openai)只需实现 _translate_one。
"""
from __future__ import annotations

import random
import threading
import time
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, List, Optional

from ..config import ProviderConfig
from ..core.tokenize import count_tokens
from .prompts import build_system_prompt


class RateLimiter:
    """令牌桶限速:限制每秒请求数,线程安全。"""

    def __init__(self, max_calls_per_second: float = 5.0):
        self.interval = 1.0 / max_calls_per_second if max_calls_per_second > 0 else 0.0
        self._last = 0.0
        self._lock = threading.Lock()

    def acquire(self) -> None:
        if self.interval <= 0:
            return
        with self._lock:
            now = time.time()
            wait = self.interval - (now - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.time()


# 翻译进度回调:(已完成段数, 总段数)
ProgressFn = Callable[[int, int], None]


class LLMProvider(ABC):
    name: str = "base"

    def __init__(self, cfg: ProviderConfig):
        self.cfg = cfg
        self.rate_limiter = RateLimiter(cfg.rate_limit)
        # 统计
        self.input_tokens = 0
        self.output_tokens = 0
        self.api_calls = 0
        self._stat_lock = threading.Lock()

    @abstractmethod
    def _translate_one(self, text: str, system_prompt: str) -> str:
        """翻译单段并返回译文。子类实现具体 API 调用。"""

    def _record(self, in_tok: int, out_tok: int) -> None:
        with self._stat_lock:
            self.input_tokens += in_tok
            self.output_tokens += out_tok
            self.api_calls += 1

    def _translate_with_retry(self, text: str, system_prompt: str) -> str:
        """单段翻译 + 指数退避重试;彻底失败则返回原文(保证可编译)。"""
        stripped = text.strip()
        if not stripped:
            return text  # 纯空白直接返回

        last_err: Optional[Exception] = None
        for attempt in range(self.cfg.max_retries):
            try:
                self.rate_limiter.acquire()
                result = self._translate_one(text, system_prompt)
                self._record(count_tokens(text), count_tokens(result))
                return result
            except Exception as e:  # noqa: BLE001 - 需捕获所有 API 异常做重试
                last_err = e
                # 指数退避 + 抖动
                delay = min(2 ** attempt + random.uniform(0, 1), 30)
                time.sleep(delay)
        # 全部重试失败:返回原文,让流水线继续(缺失翻译好过崩溃)
        print(f"[{self.name}] 段翻译失败,保留原文: {last_err}")
        return text

    def build_glossary(self, segments: List[str], target_lang: str = "简体中文") -> dict:
        """扫描全文高频术语,让 LLM 给出统一译法,返回术语表 dict。

        失败或无候选时返回空 dict(不影响主翻译)。
        """
        from .glossary import (
            GLOSSARY_SYSTEM_PROMPT,
            extract_candidate_terms,
            parse_glossary_response,
        )

        candidates = extract_candidate_terms(segments)
        if not candidates:
            return {}
        user = "请给出下列术语的统一中文译法:\n" + "\n".join(candidates)
        try:
            self.rate_limiter.acquire()
            resp = self._translate_one(user, GLOSSARY_SYSTEM_PROMPT)
            self._record(count_tokens(user), count_tokens(resp))
            return parse_glossary_response(resp, candidates)
        except Exception as e:  # noqa: BLE001
            print(f"[{self.name}] 术语表生成失败(忽略): {e}")
            return {}

    def translate_segments(
        self,
        segments: List[str],
        *,
        target_lang: str = "简体中文",
        max_workers: int = 8,
        on_progress: Optional[ProgressFn] = None,
        glossary: Optional[dict] = None,
    ) -> List[str]:
        """并发翻译多段,返回与输入等长、同序的译文列表。

        glossary:统一术语表,注入 system prompt 保证全文译名一致。
        """
        if not segments:
            return []
        from .glossary import format_glossary

        system_prompt = build_system_prompt(target_lang)
        if glossary:
            system_prompt += format_glossary(glossary)
        results: List[Optional[str]] = [None] * len(segments)
        done = 0
        done_lock = threading.Lock()

        def work(i: int) -> None:
            nonlocal done
            results[i] = self._translate_with_retry(segments[i], system_prompt)
            with done_lock:
                done += 1
                if on_progress:
                    on_progress(done, len(segments))

        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            list(ex.map(work, range(len(segments))))

        return [r if r is not None else segments[i] for i, r in enumerate(results)]

    def stats(self) -> dict:
        return {
            "provider": self.name,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "api_calls": self.api_calls,
        }
