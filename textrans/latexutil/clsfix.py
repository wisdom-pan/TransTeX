"""修复 .cls 文件以兼容 XeLaTeX。

跳过 inputenc/fontenc(XeLaTeX 原生 UTF-8)与拉丁字体包(避免覆盖 CJK 字体)。
从旧 main.py 的 _fix_cls_for_xelatex 迁移。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Callable

Logger = Callable[[str], None]

# 需要在非 XeLaTeX 下才加载的包(用 \ifdefined\XeTeXversion 包裹)
_GUARDED_PATTERNS = [
    r"(\\RequirePackage\[[^\]]*\]\{inputenc\})",
    r"(\\RequirePackage\[T1\]\{fontenc\})",
    r"(\\RequirePackage\{XCharter\})",
    r"(\\RequirePackage\[xcharter[^\]]*\]\{newtxmath\})",
    r"(\\RequirePackage\[scaled=[0-9.]+\]\{zlmtt\})",
    r"(\\RequirePackage\{mathptmx\})",
    r"(\\RequirePackage\{times\})",
    r"(\\RequirePackage\{palatino\})",
    r"(\\RequirePackage\{tgtermes\})",
    r"(\\RequirePackage\{newtxtext\})",
    r"(\\RequirePackage\{newtxmath\})",
]

# pdfTeX 专有命令(整行捕获:组1=行首缩进,组2=命令本体)。
# 用 \ifdefined\pdfoutput ... \fi 包裹,仅 pdfTeX 下执行。
_PDFTEX_ONLY_PATTERNS = [
    r"^([ \t]*)(\\pdfoutput\s*=\s*\d+)[ \t]*$",
    r"^([ \t]*)(\\DisableLigatures(?:\[[^\]]*\])?\{[^}]*\})[ \t]*$",
]


def fix_cls_for_xelatex(cls_file: Path, log: Logger = print) -> None:
    try:
        content = cls_file.read_text(encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        log(f"⚠️ 读取 .cls 失败: {e}")
        return

    original = content
    for pat in _GUARDED_PATTERNS:
        content = re.sub(pat, r"\\ifdefined\\XeTeXversion\\else\n\1\n\\fi", content)

    # pdfTeX 专有命令在 XeTeX 下未定义/不可用:
    #   \pdfoutput=1        → "Undefined control sequence" 并连锁 "Missing \begin{document}"、无产物(致命)
    #   \DisableLigatures   → microtype 报 "only possible with pdftex" 并中断 -halt-on-error(可致命)
    # 统一用 \ifdefined\pdfoutput 包裹整行,仅 pdfTeX 引擎下执行,XeLaTeX 下安全跳过。
    for pat in _PDFTEX_ONLY_PATTERNS:
        content = re.sub(
            pat,
            r"\1\\ifdefined\\pdfoutput \2 \\fi",
            content,
            flags=re.MULTILINE,
        )

    if content != original:
        try:
            cls_file.write_text(content, encoding="utf-8")
            log("🔧 已修复 .cls 以兼容 XeLaTeX")
        except Exception as e:  # noqa: BLE001
            log(f"⚠️ 写回 .cls 失败: {e}")
