"""二值掩码:标记 LaTeX 源码中每个字符「翻译」还是「保护」。

设计(算法思想借鉴 gpt_academic,代码为 clean-room 原创):
  - 维护一个与源码等长的 uint8 数组,初值全部 TRANSFORM。
  - 一系列 `preserve_*` 规则把公式、命令、环境、引用等区域置为 PRESERVE。
  - 一系列 `reverse_*` 规则把某些被保护区域的「内部文本」重新挖回 TRANSFORM
    (例如 \caption{...} 的框架保护、括号内文字翻译)。

这样 LLM 永远看不到需要保护的内容,从根本上杜绝命令被翻译 / 对齐崩坏。
"""
from __future__ import annotations

import re
from typing import Iterable

import numpy as np

from ..types import PRESERVE, TRANSFORM


def build_mask(text: str) -> np.ndarray:
    """返回与 text 等长、全部标记为 TRANSFORM 的掩码。"""
    return np.full(len(text), TRANSFORM, dtype=np.uint8)


# --------------------------------------------------------------------------- #
# 基础操作
# --------------------------------------------------------------------------- #
def preserve(text: str, mask: np.ndarray, pattern: str, flags: int = 0) -> None:
    """把所有匹配 pattern 的区间标记为 PRESERVE(整段保护)。"""
    for m in re.finditer(pattern, text, flags):
        mask[m.start():m.end()] = PRESERVE


def preserve_many(text: str, mask: np.ndarray, patterns: Iterable[str], flags: int = 0) -> None:
    for p in patterns:
        preserve(text, mask, p, flags)


def _find_matching_brace(text: str, open_pos: int) -> int:
    """给定 '{' 的位置,返回配对 '}' 的位置(含转义处理)。找不到返回 -1。"""
    depth = 0
    i = open_pos
    n = len(text)
    while i < n:
        c = text[i]
        if c == "\\":  # 跳过转义字符,如 \{ \}
            i += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def preserve_careful_brace(text: str, mask: np.ndarray, prefix_pattern: str) -> None:
    """保护「命令 + 配平花括号」整体,支持嵌套花括号。

    prefix_pattern 应匹配到 '{' 之前(不含 '{'),例如 r"\\hl" 匹配 \hl 后面紧跟 {...}。
    """
    for m in re.finditer(prefix_pattern, text):
        brace_start = text.find("{", m.end() - 1 if m.end() > m.start() else m.end())
        # 命令名后必须紧跟 '{'(允许中间无空格)
        j = m.end()
        while j < len(text) and text[j] in " \t":
            j += 1
        if j >= len(text) or text[j] != "{":
            continue
        close = _find_matching_brace(text, j)
        if close == -1:
            continue
        mask[m.start():close + 1] = PRESERVE


def preserve_env(
    text: str,
    mask: np.ndarray,
    env_names: Iterable[str],
    max_lines: int | None = None,
) -> None:
    r"""保护 \begin{env}...\end{env} 环境。

    若指定 max_lines,则仅保护行数 <= max_lines 的环境
    (超长环境留待其内部子规则处理,避免整章被吞掉)。
    """
    for env in env_names:
        # env 名允许带 * 号;\1 反向引用确保 begin/end 配对
        pattern = r"\\begin\{(" + re.escape(env) + r"\*?)\}(.*?)\\end\{\1\}"
        for m in re.finditer(pattern, text, re.DOTALL):
            if max_lines is not None:
                n_lines = m.group(0).count("\n")
                if n_lines > max_lines:
                    continue
            mask[m.start():m.end()] = PRESERVE


# --------------------------------------------------------------------------- #
# reverse:从保护区域中挖回「需要翻译的内部文本」
# --------------------------------------------------------------------------- #
# 透明格式命令:其花括号内部是需要翻译的正文,reverse 后不应把内部重新保护,
# 只保护命令 token 本身(如 \center{文字} \textbf{文字} 里的文字要翻译)。
_TRANSPARENT_WRAP_CMDS = {
    "center", "centering", "textbf", "textit", "emph", "text", "texttt",
    "textsc", "textsf", "textrm", "underline", "bf", "it", "sc", "sl",
    "large", "Large", "LARGE", "huge", "Huge", "small", "footnotesize",
    "normalsize", "mbox", "hbox", "textnormal", "mathrm",
}


def _reprotect_inline(text: str, mask: np.ndarray, start: int, end: int) -> None:
    r"""在 [start, end) 这段「挖回翻译」的区域内,重新保护嵌套的命令 / 数学 / 换行。

    reverse 会把整个花括号内部标记为 TRANSFORM,会覆盖掉之前对嵌套 \ref{}、
    \\、$...$、\titlesubtitle{} 等的保护。这里把它们重新置为 PRESERVE,
    使 LLM 只看到纯文本(修复 \title 里 \\[-0.15em]\titlesubtitle{} 被翻坏)。

    例外:透明格式命令(\center \textbf 等)只保护命令 token,其花括号内容保持翻译
    (修复 \title{\center{Orca: ...}} 里标题文字未翻译)。
    """
    region = text[start:end]
    # 1) 命令 + 花括号参数:\cmd{...}(含嵌套),整体保护
    for m in re.finditer(r"\\([a-zA-Z]+)\*?", region):
        cmd_name = m.group(1)
        cmd_start = start + m.start()
        j = start + m.end()
        # 跳过命令后可选的 [..] 参数
        k = j
        while k < end and text[k] in " \t":
            k += 1
        if k < end and text[k] == "[":
            bracket_close = text.find("]", k)
            if bracket_close != -1 and bracket_close < end:
                k = bracket_close + 1
        # 若紧跟 { ,连同配平花括号一起保护
        kk = k
        while kk < end and text[kk] in " \t":
            kk += 1
        if kk < end and text[kk] == "{":
            close = _find_matching_brace(text, kk)
            if close != -1 and close < end:
                if cmd_name in _TRANSPARENT_WRAP_CMDS:
                    # 透明格式命令:只保护 \cmd{ 和 } 定界符,内部文字仍翻译
                    mask[cmd_start:kk + 1] = PRESERVE  # \cmd...{
                    mask[close:close + 1] = PRESERVE    # }
                    # 递归处理内部(可能还有嵌套命令 / 更深的 \center)
                    _reprotect_inline(text, mask, kk + 1, close)
                else:
                    mask[cmd_start:close + 1] = PRESERVE
                continue
        # 否则只保护命令本身(+ 可选 [..] 参数)到 k
        mask[cmd_start:k] = PRESERVE
    # 2) 行内数学 $...$
    for m in re.finditer(r"(?<!\\)\$(?:\\.|[^$\\])+\$", region):
        mask[start + m.start():start + m.end()] = PRESERVE
    # 3) 转义换行 \\ 及其可选间距 \\[..](上面命令扫描已覆盖 \\,此处兜底 \\ 无字母的情况)
    for m in re.finditer(r"\\\\(?:\[[^\]]*\])?", region):
        mask[start + m.start():start + m.end()] = PRESERVE


def reverse_careful_brace(text: str, mask: np.ndarray, prefix_pattern: str,
                          min_pos: int = 0) -> None:
    r"""对 \cmd{...},保护框架(\cmd{ 和 }),把花括号内部标记回 TRANSFORM。

    例:\caption{This is a figure} → 只翻译 "This is a figure"。
    min_pos:仅处理起始位置 >= min_pos 的匹配(用于把格式命令限制在正文 body 内,
    避免翻译 preamble 里 \newcommand 定义中的 \textbf{...} 模板)。
    """
    for m in re.finditer(prefix_pattern, text):
        if m.start() < min_pos:
            continue
        j = m.end()
        while j < len(text) and text[j] in " \t":
            j += 1
        if j >= len(text) or text[j] != "{":
            continue
        close = _find_matching_brace(text, j)
        if close == -1:
            continue
        # 先整体保护(框架),再把内部挖回翻译
        mask[m.start():close + 1] = PRESERVE
        inner_start, inner_end = j + 1, close  # 不含两端花括号
        if inner_end > inner_start:
            mask[inner_start:inner_end] = TRANSFORM
            _reprotect_inline(text, mask, inner_start, inner_end)


def reverse_wrapped_env(text: str, mask: np.ndarray, env_names: Iterable[str]) -> None:
    r"""对 \begin{env}...\end{env},保护 begin/end 定界符,内部文本挖回翻译。

    例:\begin{abstract} ... \end{abstract} 的正文需要翻译。
    """
    for env in env_names:
        pattern = r"(\\begin\{" + re.escape(env) + r"\})(.*?)(\\end\{" + re.escape(env) + r"\})"
        for m in re.finditer(pattern, text, re.DOTALL):
            mask[m.start():m.end()] = PRESERVE  # 先整体保护
            inner_start, inner_end = m.start(2), m.end(2)
            if inner_end > inner_start:
                mask[inner_start:inner_end] = TRANSFORM  # 正文挖回翻译
                _reprotect_inline(text, mask, inner_start, inner_end)


# --------------------------------------------------------------------------- #
# 规则装配:顺序很重要(先大范围保护,最后 reverse 挖回)
# --------------------------------------------------------------------------- #

# 数学 / 公式环境(整段保护)
_MATH_ENVS = [
    "equation", "align", "aligned", "multline", "gather", "eqnarray",
    "math", "displaymath", "array", "cases", "split", "flalign",
]
# 图表 / 浮动体(整段保护;caption 随后由 reverse 挖回)
_FLOAT_ENVS = [
    "figure", "table", "wrapfigure", "wraptable", "sidewaystable",
    "sidewaysfigure", "subfigure", "tabular", "tabularx", "longtable",
]
# 代码 / 逐字环境(整段保护)
_CODE_ENVS = ["lstlisting", "verbatim", "minted", "Verbatim", "algorithm", "algorithmic"]

# 需要翻译内部文本的命令(框架保护、内容翻译)
# 分两组:元信息命令在 preamble 也要翻译;格式命令仅在正文 body 内翻译
# (避免把 \newcommand 定义里的 \textbf{...} 模板文本当正文翻译)
# 注意:\author 不翻译(人名保持原文),故不在此列——由 preamble 保护即可。
_REVERSE_META_CMDS = [
    r"\\caption", r"\\subcaption", r"\\title",
    r"\\abstract",  # 部分 cls(如 fairmeta)用 \abstract{...} 命令形式
    r"\\titlesubtitle",  # 自定义副标题命令,内部纯文本需翻译
]
_REVERSE_BODY_CMDS = [
    r"\\section", r"\\section\*", r"\\subsection", r"\\subsection\*",
    r"\\subsubsection", r"\\subsubsection\*", r"\\paragraph", r"\\textbf",
    r"\\textit", r"\\emph", r"\\text",
]
# 需要翻译正文的环境
_REVERSE_ENVS = ["abstract", "quote", "quotation"]

# 自定义单参文本宏:\newcommand{\x}[1]{ ...#1... },且 #1 作为可见正文出现
# (常见于高亮/批注宏,如 \jyh \ryan \textbl)。这类宏的 #1 内容需要翻译。
# 排除明显非文本的宏(url/label/ref/cite/包含 \verb 等)。
_MACRO_DEF_RE = re.compile(
    r"\\(?:re)?newcommand\s*\{?\\([a-zA-Z]+)\}?\s*\[1\]\s*(?:\[[^\]]*\])?\s*\{(.*)"
)
_MACRO_NAME_BLOCKLIST = {
    "label", "ref", "cite", "url", "href", "input", "include",
    "includegraphics", "eqref", "autoref", "cref", "footnote",
}


def detect_text_macros(text: str) -> list[str]:
    r"""从 preamble 检测「单参文本包装宏」,返回其正则前缀列表(如 [r"\\jyh"])。

    条件:\newcommand{\x}[1]{...} 且宏体里出现独立的 #1(作为正文输出),
    宏名不在黑名单,#1 不是被 \verb/\url 等吞掉。
    """
    found: list[str] = []
    for m in _MACRO_DEF_RE.finditer(text):
        name = m.group(1)
        if name in _MACRO_NAME_BLOCKLIST:
            continue
        body = m.group(2)
        # 宏体里必须有作为参数输出的 #1
        if "#1" not in body:
            continue
        # 排除把 #1 放进 \url/\verb/\lstinline 的情况(非自然语言)
        if re.search(r"\\(?:url|verb|lstinline|texttt|path)\b[^\n]*#1", body):
            continue
        found.append(r"\\" + re.escape(name))
    return found


def apply_default_rules(text: str) -> np.ndarray:
    r"""对整篇(已合并的)LaTeX 源码计算掩码。

    返回 uint8 掩码数组。规则顺序:
      1) 保护 preamble(\begin{document} 之前的一切)
      2) 保护匿名公式 $...$ / $$...$$ / \[...\]
      3) 保护公式 / 图表 / 代码环境
      4) 保护参考文献、引用、标签、格式命令等
      5) reverse:把 caption / 章节标题 / abstract 等的内部文本挖回翻译
    """
    mask = build_mask(text)

    # 1) preamble:\begin{document} 之前全部保护
    doc_begin = re.search(r"\\begin\{document\}", text)
    if doc_begin:
        mask[:doc_begin.end()] = PRESERVE
    # \end{document} 之后也保护
    doc_end = re.search(r"\\end\{document\}", text)
    if doc_end:
        mask[doc_end.start():] = PRESERVE

    # \iffalse ... \fi 条件注释块
    preserve(text, mask, r"\\iffalse.*?\\fi", re.DOTALL)

    # \makeatletter ... \makeatother 之间是底层 TeX 代码(含 @ 命令),整块保护
    preserve(text, mask, r"\\makeatletter.*?\\makeatother", re.DOTALL)
    # 分组 / TeX 底层命令(不含可翻译文本)
    preserve(text, mask, r"\\(?:begingroup|endgroup|makeatletter|makeatother)")

    # LaTeX 行注释:未转义的 % 到行尾(不含换行)。必须早于其他规则,
    # 以免把注释里的内容当正文翻译,也避免 fix_content 误转义真实注释符。
    preserve(text, mask, r"(?<!\\)%[^\n]*")

    # 2) 行内 / 行间数学(顺序:先长后短,避免 $$ 被 $ 拆开)
    preserve(text, mask, r"\$\$.*?\$\$", re.DOTALL)
    preserve(text, mask, r"\\\[.*?\\\]", re.DOTALL)
    preserve(text, mask, r"(?<!\\)\$(?:\\.|[^$\\])+\$")  # 行内 $...$(处理转义 \$)

    # 3) 公式 / 图表 / 代码环境
    preserve_env(text, mask, _MATH_ENVS)
    preserve_env(text, mask, _FLOAT_ENVS)
    preserve_env(text, mask, _CODE_ENVS)

    # 4) 参考文献与引用类命令(整行 / 整块保护)
    preserve(text, mask, r"\\begin\{thebibliography\}.*?\\end\{thebibliography\}", re.DOTALL)
    preserve_many(text, mask, [
        r"\\bibliography\{[^}]*\}",
        r"\\bibliographystyle\{[^}]*\}",
        r"\\cite[a-zA-Z]*\s*(?:\[[^\]]*\])*\{[^}]*\}",
        r"\\ref\{[^}]*\}", r"\\eqref\{[^}]*\}", r"\\pageref\{[^}]*\}",
        r"\\autoref\{[^}]*\}", r"\\cref\{[^}]*\}", r"\\Cref\{[^}]*\}",
        r"\\label\{[^}]*\}",
        r"\\url\{[^}]*\}", r"\\href\{[^}]*\}\{",  # href 第一参数保护,文字随后可翻译
        r"\\includegraphics(?:\[[^\]]*\])?\{[^}]*\}",
        r"\\input\{[^}]*\}", r"\\include\{[^}]*\}",
        r"\\usepackage(?:\[[^\]]*\])?\{[^}]*\}",
        r"\\newcommand[^\n]*", r"\\renewcommand[^\n]*", r"\\def[^\n]*",
    ])
    # 格式 / 排版命令
    preserve_many(text, mask, [
        r"\\vspace\*?\{[^}]*\}", r"\\hspace\*?\{[^}]*\}",
        r"\\begin\{[^}]*\}", r"\\end\{[^}]*\}",  # 残余 begin/end 定界符
        r"\\clearpage", r"\\newpage", r"\\appendix",
        r"\\tableofcontents", r"\\maketitle", r"\\item(?=\s)",
        r"\\footnote\{",  # \footnote{ 框架保护,内容随后翻译
    ])

    # 5) reverse:挖回需要翻译的内部文本(框架保持保护)
    #    - 元信息命令(title/author/abstract)在 preamble 也翻译
    #    - 格式命令(textbf/emph/section)仅在正文 body 内翻译,避免碰 \newcommand 模板
    body_start = doc_begin.end() if doc_begin else 0
    for cmd in _REVERSE_META_CMDS:
        reverse_careful_brace(text, mask, cmd)
    for cmd in _REVERSE_BODY_CMDS:
        reverse_careful_brace(text, mask, cmd, min_pos=body_start)
    # 自定义单参文本宏(如 \jyh{...} \ryan{...}):正文内挖回其 #1 内容翻译
    for cmd in detect_text_macros(text):
        reverse_careful_brace(text, mask, cmd, min_pos=body_start)
    reverse_wrapped_env(text, mask, _REVERSE_ENVS)

    # 6) 最后再次保护注释:reverse 可能把被注释掉的命令内部(如 `% \title{...}`)
    #    重新挖成翻译。注释保护必须最终生效,确保被注释的内容永不翻译。
    preserve(text, mask, r"(?<!\\)%[^\n]*")

    return mask


def render_debug_html(text: str, mask: np.ndarray) -> str:
    """生成掩码可视化 HTML:红=保护,黑=翻译。用于人工核对规则正确性。"""
    from html import escape

    parts = ['<html><head><meta charset="utf-8"><style>'
             'body{font-family:monospace;white-space:pre-wrap;line-height:1.5;padding:16px}'
             '.p{color:#c0392b}.t{background:#eafaf1;color:#111}'
             '</style></head><body>']
    i, n = 0, len(text)
    while i < n:
        cur = mask[i]
        j = i
        while j < n and mask[j] == cur:
            j += 1
        cls = "p" if cur == PRESERVE else "t"
        parts.append(f'<span class="{cls}">{escape(text[i:j])}</span>')
        i = j
    parts.append("</body></html>")
    return "".join(parts)
