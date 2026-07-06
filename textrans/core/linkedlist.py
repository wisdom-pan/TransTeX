"""链表:把 (文本, 掩码) 转成交替的「保护段 / 翻译段」节点序列。

只有 preserve=False 的节点会被送去翻译;合并时按节点顺序拼回,
不依赖任何编号,从根本上杜绝对齐崩坏。

算法思想借鉴 gpt_academic,代码 clean-room 原创。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List

import numpy as np

from ..types import PRESERVE, TRANSFORM

# 短于此长度的翻译段直接改为保护(多为孤立符号、单词,翻译无意义且易出错)
MIN_TRANSLATE_LEN = 12

# 至少含一个「实义词」才值得翻译:一段字母(≥2)或任意 CJK 字符。
# 用于跳过纯符号/数字/单字母碎片,同时保留 "video"/"the maximum" 这类短语。
_HAS_WORD_RE = re.compile(r"[A-Za-z]{2,}|[一-鿿]")


def _has_translatable_word(s: str) -> bool:
    # 去掉命令与花括号后仍有实义词才翻译(避免把 \ref 等残片当正文)
    stripped = re.sub(r"\\[a-zA-Z]+|[{}]", " ", s)
    return bool(_HAS_WORD_RE.search(stripped))


@dataclass
class Node:
    string: str
    preserve: bool
    line_start: int = 0  # 该节点在全文中的起始行号(0-based)
    line_end: int = 0    # 结束行号(含)

    @property
    def line_range(self) -> tuple[int, int]:
        return (self.line_start, self.line_end)


def convert_to_linklist(text: str, mask: np.ndarray) -> List[Node]:
    """相邻且同类(同 preserve 标记)的字符合并为一个节点。"""
    if not text:
        return []
    nodes: List[Node] = []
    i, n = 0, len(text)
    while i < n:
        cur = mask[i]
        j = i
        while j < n and mask[j] == cur:
            j += 1
        nodes.append(Node(string=text[i:j], preserve=(cur == PRESERVE)))
        i = j
    return nodes


def _brace_balance(s: str) -> int:
    """返回花括号净层级(忽略转义 \\{ \\})。"""
    depth = 0
    i, n = 0, len(s)
    while i < n:
        c = s[i]
        if c == "\\":
            i += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        i += 1
    return depth


def post_process(nodes: List[Node], full_text: str) -> List[Node]:
    """对节点序列做四步整理,然后标注行号。

    1) 花括号不平衡的翻译段 → 改为保护(避免把半个命令送去翻译)
    2) 过短的翻译段 → 改为保护
    3) 空白脱离:翻译段首尾的空白/换行归还给相邻保护段
       —— 这是命令粘连 (\\quad Kernel → \\quadKernel) 的正解
    4) 合并相邻的同类节点;标注每个节点的行号范围
    """
    # 1) + 2) 降级不合格的翻译段
    for node in nodes:
        if node.preserve:
            continue
        if _brace_balance(node.string) != 0:
            node.preserve = True
        elif not _has_translatable_word(node.string):
            node.preserve = True

    # 3) 空白脱离:把翻译段两端的空白移交相邻保护段
    _detach_boundary_whitespace(nodes)

    # 4) 合并相邻同类节点
    merged: List[Node] = []
    for node in nodes:
        if not node.string:
            continue
        if merged and merged[-1].preserve == node.preserve:
            merged[-1].string += node.string
        else:
            merged.append(node)

    _annotate_lines(merged)
    return merged


def _detach_boundary_whitespace(nodes: List[Node]) -> None:
    """将翻译段首尾的空白转移到相邻节点,使 LLM 只看到实义文本。

    翻译段前导空白 → 上一节点末尾;尾随空白 → 下一节点开头。
    若相邻节点不存在,则空白留在原节点(不丢失)。
    """
    n = len(nodes)
    for idx, node in enumerate(nodes):
        if node.preserve or not node.string:
            continue
        # 前导空白
        lead_len = len(node.string) - len(node.string.lstrip())
        if lead_len and idx > 0:
            nodes[idx - 1].string += node.string[:lead_len]
            node.string = node.string[lead_len:]
        # 尾随空白
        if node.string:
            trail_len = len(node.string) - len(node.string.rstrip())
            if trail_len and idx < n - 1:
                nodes[idx + 1].string = node.string[-trail_len:] + nodes[idx + 1].string
                node.string = node.string[:-trail_len]


def _annotate_lines(nodes: List[Node]) -> None:
    """按累计换行数标注每个节点的起止行号(0-based)。"""
    line = 0
    for node in nodes:
        node.line_start = line
        nl = node.string.count("\n")
        node.line_end = line + nl
        line += nl


def extract_translatable(nodes: List[Node]) -> List[str]:
    """按顺序取出所有需要翻译的段文本。"""
    return [node.string for node in nodes if not node.preserve]
