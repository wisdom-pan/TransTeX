"""LatexMerger:把翻译结果按链表顺序拼回完整 LaTeX。

关键点:
  - 保护段原样保留。
  - 翻译段先聚合其(可能被切分的)子块,过 fix_content 修复。
  - 若该翻译段的行号命中编译报错行,则回退为原文(编译日志驱动修复)。
  - 完全按顺序对齐,无编号回填。
"""
from __future__ import annotations

import re
from typing import List, Optional

from ..types import SegmentStats
from .fix import fix_content
from .linkedlist import Node
from .split import SplitResult


class LatexMerger:
    def __init__(self, split_result: SplitResult):
        self.sr = split_result

    def _aggregate_chunks(self, translated_chunks: List[str]) -> List[str]:
        """把扁平的 chunk 译文聚合回「每个翻译节点一条」。"""
        n_nodes = self.sr.n_translatable_nodes
        buckets: List[List[str]] = [[] for _ in range(n_nodes)]
        for owner, text in zip(self.sr.chunk_owner, translated_chunks):
            buckets[owner].append(text)
        return ["".join(b) for b in buckets]

    def merge(
        self,
        translated_chunks: List[str],
        *,
        buggy_lines: Optional[List[int]] = None,
        surgery_radius: int = 5,
        stats: Optional[SegmentStats] = None,
    ) -> str:
        """按链表顺序拼回;命中 buggy_lines 的翻译段回退原文。"""
        buggy = set(buggy_lines or [])
        per_node = self._aggregate_chunks(translated_chunks)

        out: List[str] = []
        t_idx = 0
        for node in self.sr.nodes:
            if node.preserve:
                out.append(node.string)
                continue

            original = node.string
            translated = per_node[t_idx] if t_idx < len(per_node) else ""
            t_idx += 1

            fixed = fix_content(translated, original) if translated else original

            # 编译日志回退:该节点行号范围附近有报错 → 用原文
            if buggy and self._hits_buggy(node, buggy, surgery_radius):
                fixed = original
                if stats is not None:
                    stats.reverted_on_compile += 1

            out.append(fixed)

        result = "".join(out)
        # 跨节点边界修复:保护段结尾的 \command 紧贴翻译段开头的 CJK
        #(如 \title{\sys高效...} 里 \sys 与中文粘连),xeCJK 下会被当成未定义控制词。
        result = re.sub(r"(\\[a-zA-Z]+)(?=[一-鿿　-〿＀-￯])", r"\1{}", result)
        return result

    @staticmethod
    def _hits_buggy(node: Node, buggy: set[int], radius: int) -> bool:
        lo = node.line_start - radius
        hi = node.line_end + radius
        return any(lo <= b <= hi for b in buggy)
