"""译文级修复:在合并前对每个翻译段做安全修复,替代旧的 fix_*.py 脚本。

核心原则:修复必须保守——若译文破坏了 LaTeX 结构(命令数不符、括号不平衡),
宁可整段/部分回退到原文,也不产出无法编译的内容。

算法思想借鉴 gpt_academic 的 fix_content,代码 clean-room 原创。
"""
from __future__ import annotations

import re


def _brace_balance(s: str) -> int:
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


def _structural_counts(s: str) -> dict:
    r"""统计「结构性命令」的出现次数(按命令名分桶)。

    只有结构性命令(环境定界、列表项)的数量失配才会破坏编译,才据此回退。
    其余内联命令(命名宏 \sys \method、格式宏 \textbf \texttt、\noindent \S 等)
    翻译时被丢弃/复用属常见现象且不影响可编译性:
      - 带花括号的格式宏若整体丢失,花括号成对消失,由括号平衡校验兜底;
      - 无花括号的命名/间距宏丢失只是丢了个词或排版微调,不该让整段回退英文。
    过去用「全部命令精确等数」做校验,导致 LLM 少译一个 \sys 就把整段中文
    回退成英文原文(实测语料中 130+ 段正文因此未翻译)。改为只校验结构性命令。
    """
    counts: dict[str, int] = {}
    for c in re.findall(r"\\([a-zA-Z]+)", s):
        name = c.lower()
        if name in _STRUCTURAL_CMDS:
            counts[name] = counts.get(name, 0) + 1
    return counts


# 结构性命令:数量失配会破坏 LaTeX 编译(环境定界、列表结构),必须严格匹配。
_STRUCTURAL_CMDS = {
    "begin", "end", "item",
    "squishlist", "squishlisttwo", "squishend",  # 常见自定义紧凑列表宏
    "itemize", "enumerate", "description",
}


# 模型偶尔会输出的元信息 / 拒答话术,命中则视为翻译失败。
# 注意:这些串必须是「几乎只可能出现在拒答/元话术里」的。曾误收 "作为一个",
# 但它是极常见的正文措辞(如「作为一个通用世界基础模型」「作为一个耦合的技能栈」),
# 会把正常中文段落误判为拒答并回退英文;拒答话术改由更具体的 "作为AI" 等捕获。
_META_PATTERNS = [
    "请提供", "需要翻译的", "以下是翻译", "翻译如下", "翻译结果",
    "的中文翻译", "抱歉", "无法翻译", "作为AI", "作为一个AI", "作为一名AI",
    "作为语言模型", "作为一个语言模型",
    "[Local Message]", "Traceback", "```",
]

# 模型自行添加的结构标记,应剥离
_STRAY_TAG = re.compile(r"^\s*\[(章节标题|图表标题|注释|摘要|标题|正文|段落|title|caption|section)\]\s*", re.I)


def _looks_like_meta(translated: str) -> bool:
    t = translated.strip()
    if not t:
        return True
    for p in _META_PATTERNS:
        if p in t:
            return True
    return False


def _strip_stray_tags(s: str) -> str:
    prev = None
    while prev != s:
        prev = s
        s = _STRAY_TAG.sub("", s)
    return s


def _brace_delta(s: str) -> int:
    """单行内 `{` 与 `}` 的净深度增量(跳过 `\X` 转义,与 _brace_balance 同口径)。"""
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


def _collapse_blank_in_args(s: str) -> str:
    r"""折叠命令参数内的空行,避免 `\par` 打断非 `\long` 命令参数。

    LLM 译文常把 `\textbf{术语}` 拆成 `\textbf{\\n\\n术语}`,空行在非 `\\long`
    命令参数里会触发 ``! Paragraph ended before \\text@command was complete``,
    进而触发日志驱动修复把整段回退成英文(表现为"该段没被翻译")。
    只折叠「自上一行起括号仍未闭合(深度>0)」的空行;深度为 0 处的空行
    (段落正文、`\\begin`/`\\end` 环境体)原样保留。删掉空行后前后各留一个
    换行,TeX 视作单个空格,既不断词也不产生 `\\par`。
    """
    lines = s.split("\n")
    out: list[str] = []
    depth = 0
    for line in lines:
        if line.strip() == "" and depth > 0:
            continue  # 参数内的空行:删掉,保留单个换行=空格,避免 \par
        out.append(line)
        depth = max(0, depth + _brace_delta(line))
    return "\n".join(out)


_SUBSUP_RE = re.compile(r"(?<!\\)([_^])")
_INLINE_MATH_RE = re.compile(r"\$.*?\$", re.DOTALL)


def _escape_subsup(s: str) -> str:
    r"""转义裸 _ 和 ^(未被 \ 前置),跳过 $...$ 行内数学区。

    见 fix_content 的 1b 步说明:兜住 LLM 丢失 \textsc{move\_to} 的 \ 后产生的
    裸下标/上标,避免 "Missing $" 级联吃掉参考文献。
    """
    out: list[str] = []
    last = 0
    for m in _INLINE_MATH_RE.finditer(s):
        out.append(_SUBSUP_RE.sub(r"\\\1", s[last:m.start()]))
        out.append(m.group(0))  # 数学区原样保留
        last = m.end()
    out.append(_SUBSUP_RE.sub(r"\\\1", s[last:]))
    return "".join(out)


def _join_most(translated: str, original: str) -> str:
    """括号不平衡时的部分回退:取译文中括号已平衡的最长前缀,后半接原文。

    简化实现:逐字符累计括号层级,记录最后一次层级归零的位置作为切点。
    """
    depth = 0
    last_balanced = 0
    i, n = 0, len(translated)
    while i < n:
        c = translated[i]
        if c == "\\":
            i += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        i += 1
        if depth == 0:
            last_balanced = i
    if last_balanced == 0:
        return original
    return translated[:last_balanced] + " " + original


def fix_content(translated: str, original: str) -> str:
    """对单个翻译段做安全修复;不安全则回退原文。"""
    if _looks_like_meta(translated):
        return original

    fixed = _strip_stray_tags(translated)

    # 0) 折叠命令参数内的空行(LLM 常把 \textbf{X} 拆成跨空行,导致 \par 打断参数)
    fixed = _collapse_blank_in_args(fixed)

    # 1) 转义裸 %(LaTeX 注释符;中文语境的百分号必须写成 \%)
    fixed = re.sub(r"(?<!\\)%", r"\\%", fixed)

    # 1b) 转义裸 _ 和 ^(未被 \ 前置的),跳过 $...$ 数学区。
    #     LLM 常把原文 \textsc{move\_to} 的 \ 丢成 move_to,裸 _ 在文本模式触发
    #     "! Missing $ inserted.",并级联:错误恢复把后续(含 \bibliography)卷入
    #     math 恢复态 → \bibliography 不写 \bibdata → bibtex 不跑 → 参考文献整段
    #     消失、正文格式错乱。per-chunk 补一道兜底转义。数学由 splitter 保护、
    #     不出现在翻译段,但仍跳过 $...$ 以防 LLM 自带 $。
    fixed = _escape_subsup(fixed)

    # 2) 修命令与花括号间的多余空格:\cmd { → \cmd{ ,  \ cmd{ → \cmd{
    #    只吃空格/制表符,不吃换行(\medskip\n\n{...} 的空行是段落分隔,须保留)
    fixed = re.sub(r"\\([a-zA-Z]{2,})[ \t]+\{", r"\\\1{", fixed)
    fixed = re.sub(r"\\[ \t]+([a-zA-Z]{2,})\{", r"\\\1{", fixed)

    # 3) \item 后补空格(中文直接跟命令会导致编译错误)
    fixed = re.sub(r"(\\item)(?=[^\s\[])", r"\1 ", fixed)

    # 3b) 无参命令后紧跟 CJK 字符 → 插入空格。
    #     否则 xeCJK 下 \sys高效 会被当成一个未定义的多字控制序列 \sys高效...
    #     (CJK 在 xeCJK 里可能有 letter catcode)。用 "{}" 分隔既断开控制词又不产生多余空格。
    fixed = re.sub(r"(\\[a-zA-Z]+)(?=[一-鿿　-〿＀-￯])", r"\1{}", fixed)

    # 4) 结构性命令(环境定界 / 列表项)数量失配 → 会破坏编译,整段回退。
    #    不再校验全部命令等数:内联命名/格式宏(\sys \textbf \noindent 等)
    #    被 LLM 丢弃/复用不影响可编译性,由下面的括号平衡校验兜底即可。
    if _structural_counts(fixed) != _structural_counts(original):
        return original

    # 5) 括号层级不一致 → 部分回退
    if _brace_balance(fixed) != _brace_balance(original):
        return _join_most(fixed, original)

    return fixed
