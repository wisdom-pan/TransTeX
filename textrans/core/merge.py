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
from .fix import fix_content, _collapse_blank_in_args
from .linkedlist import Node
from .split import SplitResult


# 代码/伪代码环境:其内部空行与字面 {} 不参与命令参数 depth 跟踪。
# per-chunk fix 看不到外层命令(如 \abstract{ 在保护节点)的括号,故合并完整
# 文档后需做一次全局 depth 跟踪折叠;但 verbatim/algorithm 等环境体内可能有
# 字面花括号与合法空行,必须整段跳过,否则会误删代码区空行。
_CODE_ENVS = [
    "verbatim", "Verbatim", "lstlisting", "minted",
    "algorithm", "algorithmic", "algorithm2e",
]
_VERBATIM_RE = re.compile(
    r"\\begin\{(" + "|".join(_CODE_ENVS) + r")\}.*?\\end\{\1\}",
    re.DOTALL,
)


def _collapse_doc(s: str) -> str:
    r"""文档级折叠命令参数内的空行。

    `_collapse_blank_in_args` 只在 per-chunk 上跑,看不到外层命令的括号
    (如 `\abstract{` 因单边括号被 split 划为保护节点,内文才是翻译段),
    导致 `\abstract{中文\n\n中文}` 里的空行在 chunk 内 depth=0 被保留,
    合回去后落在 `\abstract{}` 参数内触发 `\par` 致命错误。
    这里在完整文档上按真实 depth 跟踪重跑一次,跳过 verbatim 等代码环境。
    """
    out: List[str] = []
    last = 0
    for m in _VERBATIM_RE.finditer(s):
        out.append(_collapse_blank_in_args(s[last:m.start()]))
        out.append(m.group(0))  # 代码环境原样保留
        last = m.end()
    out.append(_collapse_blank_in_args(s[last:]))
    result = "".join(out)
    # \begin{env} 后紧跟的空行会打断其可选 [opts] 参数解析
    # (\begin 扫 [ 时跳空格但不跳 \par),导致 [opts] 被当正文 → "missing \item"。
    # \begin{env} 后的空行无语义(环境体尚未开始),折叠安全。
    result = re.sub(r"(\\begin\{[^}]+\})\n[ \t]*\n+", r"\1\n", result)
    return result


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
        # 文档级折叠命令参数内的空行(per-chunk 看不到 \abstract{} 等外层括号)
        result = _collapse_doc(result)
        return result

    @staticmethod
    def _hits_buggy(node: Node, buggy: set[int], radius: int) -> bool:
        lo = node.line_start - radius
        hi = node.line_end + radius
        return any(lo <= b <= hi for b in buggy)
