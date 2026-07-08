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


def _count_commands(s: str) -> int:
    r"""统计 LaTeX 命令数(\word 形式,不含转义符 \% \& 等)。

    排除「文本缩写宏」(\eg \ie \etc 等):这类宏展开为纯文本,LLM 常把
    (\eg, ...) 直接译成(例如,……),命令数因此从 1 变 0。它们丢失不影响
    编译(可编译内容),不应据此把整段译文回退成英文原文。
    """
    cmds = re.findall(r"\\([a-zA-Z]+)", s)
    return sum(1 for c in cmds if c.lower() not in _TEXT_ABBREV_MACROS)


# 展开为纯文本的常见缩写宏:翻译时被译掉属正常,不计入命令数校验。
_TEXT_ABBREV_MACROS = {
    "eg", "ie", "etc", "cf", "etal", "vs", "wrt", "aka", "resp",
    "viz", "ea", "iid", "wlog",
}


# 模型偶尔会输出的元信息 / 拒答话术,命中则视为翻译失败
_META_PATTERNS = [
    "请提供", "需要翻译的", "以下是翻译", "翻译如下", "翻译结果",
    "的中文翻译", "抱歉", "无法翻译", "作为一个", "作为AI",
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

    # 1) 转义裸 %(LaTeX 注释符;中文语境的百分号必须写成 \%)
    fixed = re.sub(r"(?<!\\)%", r"\\%", fixed)

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

    # 4) 命令数不一致 → 说明模型翻译了/丢了命令,整段回退
    if _count_commands(fixed) != _count_commands(original):
        return original

    # 5) 括号层级不一致 → 部分回退
    if _brace_balance(fixed) != _brace_balance(original):
        return _join_most(fixed, original)

    return fixed
