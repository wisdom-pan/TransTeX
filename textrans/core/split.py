"""LatexSplitter:把(合并后的)LaTeX 源码切成可翻译片段。

产出 SplitResult:
  - nodes:       完整链表(保护段 + 翻译段),合并时按序拼回
  - chunks:      发给 LLM 的扁平文本块(过长的翻译段会被再切分)
  - chunk_owner: chunks[i] 属于第几个「翻译节点」(用于回填聚合)

不使用任何编号——顺序即对齐。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from .linkedlist import Node, convert_to_linklist, post_process
from .mask import apply_default_rules, render_debug_html
from .tokenize import split_to_token_limit


@dataclass
class SplitResult:
    nodes: List[Node]
    chunks: List[str] = field(default_factory=list)
    chunk_owner: List[int] = field(default_factory=list)  # 长度同 chunks
    _debug_text: str = ""

    @property
    def n_translatable_nodes(self) -> int:
        return sum(1 for n in self.nodes if not n.preserve)

    def debug_html(self) -> str:
        import numpy as np

        from .mask import build_mask
        from ..types import PRESERVE, TRANSFORM

        mask = build_mask(self._debug_text)
        pos = 0
        for node in self.nodes:
            end = pos + len(node.string)
            mask[pos:end] = PRESERVE if node.preserve else TRANSFORM
            pos = end
        return render_debug_html(self._debug_text, mask)


class LatexSplitter:
    def __init__(self, max_token_per_chunk: int = 1024):
        self.max_token_per_chunk = max_token_per_chunk

    def split(self, tex: str) -> SplitResult:
        mask = apply_default_rules(tex)
        nodes = convert_to_linklist(tex, mask)
        nodes = post_process(nodes, tex)

        chunks: List[str] = []
        chunk_owner: List[int] = []
        translate_idx = 0
        for node in nodes:
            if node.preserve:
                continue
            sub = split_to_token_limit(node.string, self.max_token_per_chunk)
            for piece in sub:
                chunks.append(piece)
                chunk_owner.append(translate_idx)
            translate_idx += 1

        return SplitResult(nodes=nodes, chunks=chunks, chunk_owner=chunk_owner, _debug_text=tex)
