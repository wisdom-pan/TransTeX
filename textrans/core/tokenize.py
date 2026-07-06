"""按 token 上限切分过长的待翻译段,避免单次请求超限。

采用多级退避切分:段落空行 → 单换行 → 句号 → 硬切,尽量在自然边界断开。
"""
from __future__ import annotations

import re
from functools import lru_cache
from typing import List


@lru_cache(maxsize=1)
def _encoder():
    try:
        import tiktoken

        return tiktoken.get_encoding("cl100k_base")
    except Exception:
        return None


def count_tokens(text: str) -> int:
    """估算 token 数。有 tiktoken 用精确编码,否则用字符启发式。"""
    enc = _encoder()
    if enc is not None:
        return len(enc.encode(text))
    # 回退:英文约 4 字符/token,中文约 1.5 字符/token,取折中
    return max(1, int(len(text) / 3))


_SPLIT_LEVELS = [
    "\n\n",  # 段落
    "\n",    # 行
    ". ",    # 英文句
    "。",     # 中文句
]


def split_to_token_limit(text: str, max_tokens: int) -> List[str]:
    """把 text 切成若干块,每块 token 数尽量 <= max_tokens。"""
    if count_tokens(text) <= max_tokens:
        return [text]

    for sep in _SPLIT_LEVELS:
        if sep in text:
            chunks = _split_by_sep(text, sep, max_tokens)
            if all(count_tokens(c) <= max_tokens for c in chunks):
                return chunks
            # 未全部满足则对超限块继续递归
            out: List[str] = []
            for c in chunks:
                if count_tokens(c) <= max_tokens:
                    out.append(c)
                else:
                    out.extend(split_to_token_limit(c, max_tokens))
            return out

    # 无自然分隔符 → 硬切
    return _hard_split(text, max_tokens)


def _split_by_sep(text: str, sep: str, max_tokens: int) -> List[str]:
    """按分隔符聚合,尽量塞满每块但不超限;分隔符保留在块内。"""
    pieces = text.split(sep)
    chunks: List[str] = []
    buf = ""
    for idx, piece in enumerate(pieces):
        candidate = buf + (sep if buf else "") + piece
        if buf and count_tokens(candidate) > max_tokens:
            chunks.append(buf)
            buf = piece
        else:
            buf = candidate
    if buf:
        chunks.append(buf)
    return chunks


def _hard_split(text: str, max_tokens: int) -> List[str]:
    """按字符比例硬切(最后兜底)。"""
    approx_chars = max(1, max_tokens * 3)
    return [text[i:i + approx_chars] for i in range(0, len(text), approx_chars)]
