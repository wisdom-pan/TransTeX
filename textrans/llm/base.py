"""LLMProvider 抽象:多模型翻译的统一接口。

- translate_segments 用线程池并发翻译多段,结果按输入顺序返回(future 顺序对齐)。
- 内置令牌桶限速 + 指数退避重试。
- 具体 provider(kimi/openai)只需实现 _translate_one。
"""
from __future__ import annotations

import random
import re
import threading
import time
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, List, Optional, TypeVar

from ..config import ProviderConfig
from ..core.tokenize import count_tokens
from .prompts import build_system_prompt

# 判定原文是否含「实义英文词」(去 LaTeX 命令/花括号后,仍有 >=3 连续 ASCII 字母)
_EN_WORD_RE = re.compile(r"[A-Za-z]{3,}")


def _is_failed_translation(original: str, translated: Optional[str]) -> bool:
    """判定译文是否失败:空,或原样返回英文而原文含实义英文词。

    split 已把含实义词的段标为可翻译;若模型对该段返回空串或原样英文,
    说明它没干活(常见于 Kimi 偶发返回空 content),应带提示重译一次。
    """
    if translated is None:
        return True
    t = translated.strip()
    if not t:
        return True
    if t == original.strip() and _EN_WORD_RE.search(
        re.sub(r"\\[a-zA-Z]+|[{}]", " ", original)
    ):
        return True
    return False


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

    _T = TypeVar("_T")

    def _call_with_retry(
        self,
        fn: Callable[[], _T],
        *,
        context: str,
    ) -> Optional[_T]:
        """执行一次 LLM 调用,带指数退避重试;全部失败返回 None。

        抽出此层供段翻译 / 术语表生成复用:base 层统一重试,
        provider 层(openai 等)各自 max_retries=0 不自重试。
        失败时打印底层 __cause__,避免只看到 openai 的 "Connection error." 这种无信息文案。
        """
        last_err: Optional[Exception] = None
        for attempt in range(self.cfg.max_retries):
            try:
                self.rate_limiter.acquire()
                return fn()
            except Exception as e:  # noqa: BLE001 - 需捕获所有 API 异常做重试
                last_err = e
                # 指数退避 + 抖动
                delay = min(2 ** attempt + random.uniform(0, 1), 30)
                time.sleep(delay)
        cause = getattr(last_err, "__cause__", None)
        detail = f" (原因: {cause})" if cause and str(cause) not in str(last_err) else ""
        print(f"[{self.name}] {context}失败(忽略): {last_err}{detail}")
        return None

    def _translate_with_retry(self, text: str, system_prompt: str) -> Optional[str]:
        """单段翻译 + 指数退避重试;彻底失败返回 None(交由上层兜底)。

        返回 None 表示「网络/API 彻底失败」,与「模型返回空串或原样英文」区分:
        前者是基础设施问题(如 SSL 连接错误),不应把原文伪装成译文缓存固化,
        而应让 pipeline 跳过缓存、下次重跑重译。
        """
        stripped = text.strip()
        if not stripped:
            return text  # 纯空白直接返回

        result = self._call_with_retry(
            lambda: self._translate_one(text, system_prompt),
            context="段翻译",
        )
        if result is None:
            return None  # 彻底失败:交由上层决定(不缓存、回退原文仅用于编译)
        self._record(count_tokens(text), count_tokens(result))
        return result

    def build_glossary(self, segments: List[str], target_lang: str = "简体中文") -> dict:
        """扫描全文高频术语,让 LLM 给出统一译法,返回术语表 dict。

        失败或无候选时返回空 dict(不影响主翻译)。复用 _call_with_retry,
        避免单次偶发连接错误就让术语表直接丢失。
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
        resp = self._call_with_retry(
            lambda: self._translate_one(user, GLOSSARY_SYSTEM_PROMPT),
            context="术语表生成",
        )
        if resp is None:
            return {}
        self._record(count_tokens(user), count_tokens(resp))
        return parse_glossary_response(resp, candidates)

    def translate_segments(
        self,
        segments: List[str],
        *,
        target_lang: str = "简体中文",
        max_workers: int = 8,
        on_progress: Optional[ProgressFn] = None,
        glossary: Optional[dict] = None,
    ) -> List[Optional[str]]:
        """并发翻译多段,返回与输入等长、同序的译文列表。

        返回 List[Optional[str]]:None 表示该段彻底未译出(网络/API 失败,
        且 nudge 重译也失败),交由 pipeline 决定回退原文用于编译、且不缓存。
        非空字符串(含模型原样返回的英文术语)视为「成功响应」。

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
            seg = segments[i]
            result = self._translate_with_retry(seg, system_prompt)
            # 防御:None(硬失败)或空/原样英文 → 换个问法重译一次
            if result is None or _is_failed_translation(seg, result):
                nudge = (
                    "上一轮返回为空或未翻译。请严格按规则把下面这段翻译成"
                    f"{target_lang},直接输出译文,不要解释:\n\n{seg}"
                )
                retry = self._translate_with_retry(nudge, system_prompt)
                # nudge 的成功响应会含指令前缀;只接受确实翻成了中文的重译
                if retry is not None and not _is_failed_translation(seg, retry):
                    result = retry
                else:
                    result = None  # 仍未译出:交由 pipeline 回退原文 + 不缓存
            results[i] = result
            with done_lock:
                done += 1
                if on_progress:
                    on_progress(done, len(segments))

        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            list(ex.map(work, range(len(segments))))

        return results

    def stats(self) -> dict:
        return {
            "provider": self.name,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "api_calls": self.api_calls,
        }
