"""编译 LaTeX → PDF,带编译日志驱动的自动修复。

失败时从 .log 提取报错行号,让 merger 把命中报错行的翻译段回退成原文,
再重编译,回退半径随重试次数扩大。取代旧的一堆事后 fix_*.py 脚本。
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Callable, List, Optional

from ..types import SegmentStats
from .merge import LatexMerger

Logger = Callable[[str], None]


def detect_engine(tex_content: str) -> str:
    """选择编译引擎。含 xeCJK/fontspec/ctex → xelatex(中文默认 xelatex)。"""
    return "xelatex"  # 注入中文支持后一律 xelatex


def _run(cmd: List[str], cwd: Path, timeout: int = 300) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(cmd, cwd=cwd, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None
    except FileNotFoundError:
        return None


def _compile_passes(tex_file: Path, engine: str, log: Logger) -> bool:
    """完整编译流程:引擎 → bibtex → 引擎 ×2。返回是否生成有效 PDF。"""
    work = tex_file.parent
    name = tex_file.name
    stem = tex_file.stem
    pdf = work / f"{stem}.pdf"

    _run([engine, "-interaction=nonstopmode", name], work)
    if (work / f"{stem}.aux").exists():
        _run(["bibtex", stem], work, timeout=60)
    _run([engine, "-interaction=nonstopmode", name], work)
    _run([engine, "-interaction=nonstopmode", name], work)

    return pdf.exists() and pdf.stat().st_size > 1000


def extract_buggy_lines(log_path: Path, tex_stem: str) -> List[int]:
    """从 .log 提取报错行号。匹配 `文件名.tex:行号:` 与 `l.行号` 两种。"""
    if not log_path.exists():
        return []
    text = log_path.read_text(encoding="utf-8", errors="replace")
    lines = set()
    for m in re.finditer(re.escape(tex_stem) + r"\.tex:(\d{1,6}):", text):
        lines.add(int(m.group(1)))
    for m in re.finditer(r"^l\.(\d{1,6})", text, re.MULTILINE):
        lines.add(int(m.group(1)))
    return sorted(lines)


def compile_with_repair(
    main_tex: Path,
    merger: LatexMerger,
    translated_chunks: List[str],
    *,
    max_try: int = 32,
    stats: Optional[SegmentStats] = None,
    log: Logger = print,
) -> Optional[Path]:
    """反复:合并 → 编译 → 若失败按报错行回退译文段 → 重编译。

    main_tex 会被就地写入合并结果。返回成功编译出的 PDF 路径或 None。
    """
    engine = "xelatex"
    stem = main_tex.stem
    work = main_tex.parent
    log_path = work / f"{stem}.log"

    buggy: List[int] = []
    for attempt in range(max_try):
        radius = 5 * (attempt + 1)
        merged = merger.merge(
            translated_chunks, buggy_lines=buggy, surgery_radius=radius, stats=stats
        )
        main_tex.write_text(merged, encoding="utf-8")

        if attempt == 0:
            log(f"🔧 编译引擎: {engine}")
        else:
            log(f"🔁 第 {attempt} 次修复重编译(回退 {len(buggy)} 处报错行,半径 {radius})")

        ok = _compile_passes(main_tex, engine, log)
        if ok:
            pdf = work / f"{stem}.pdf"
            log(f"✅ 编译成功: {pdf}")
            return pdf

        new_buggy = extract_buggy_lines(log_path, stem)
        if not new_buggy or set(new_buggy).issubset(set(buggy)):
            # 没有新报错行可回退,进一步重试也无意义
            log("⚠️ 无新增可回退报错行,停止修复")
            break
        buggy = sorted(set(buggy) | set(new_buggy))

    log("❌ 编译失败(已达最大重试或无可回退项)")
    return None
