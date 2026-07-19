"""中文支持注入:字体探测 + xeCJK/ctex 配置写入 preamble。

从旧 main.py 的 _find_cjk_font_path / _add_chinese_support / _build_*_config 迁移。
支持 macOS(按文件路径)与 Linux/容器(按 fontconfig 字体名)两种环境。
"""
from __future__ import annotations

import platform
import re
import shutil
import subprocess
from pathlib import Path
from typing import Callable, Dict, Optional

from .clsfix import fix_cls_for_xelatex

Logger = Callable[[str], None]

_STD_DOCCLASSES = {"article", "report", "book", "beamer"}


def find_cjk_font(log: Logger = print) -> Optional[Dict[str, str]]:
    """探测系统里的 Noto CJK 字体文件(macOS 常见路径,以及 Linux 字体目录)。

    返回单个字体文件路径 dict(main/sans/mono),供 xeCJK 用 Path= 加载;
    找不到具体 .otf 文件时返回 None,交由 _xecjk_config 用 fontconfig 名兜底。
    """
    search_dirs = [
        Path.home() / "Library" / "Fonts",
        Path("/System/Library/Fonts"),
        Path("/Library/Fonts"),
        Path("/System/Library/AssetsV2"),
        # Linux / 容器
        Path("/usr/share/fonts"),
        Path("/usr/local/share/fonts"),
        Path.home() / ".fonts",
    ]
    for d in search_dirs:
        if not d.exists():
            continue
        # macOS 上是单独的 NotoSerifCJKsc-Regular.otf;Linux 上可能同样存在
        for pattern in ("*.otf", "*.ttf"):
            for font in d.rglob(pattern):
                if "NotoSerifCJKsc-Regular" in font.name:
                    parent = font.parent
                    return {
                        "main": str(font),
                        "sans": str(parent / "NotoSansCJKsc-Regular.otf"),
                        "mono": str(parent / "NotoSansMonoCJKsc-Regular.otf"),
                    }
    return None


def _has_fontconfig_family(name: str) -> bool:
    """用 fc-list 检测系统是否注册了某中文字体族(Linux/容器)。"""
    if not shutil.which("fc-list"):
        return False
    try:
        out = subprocess.run(
            ["fc-list", ":lang=zh"], capture_output=True, text=True, timeout=10
        ).stdout
        return name in out
    except Exception:  # noqa: BLE001
        return False


def _xecjk_config(log: Logger) -> str:
    # 1) 优先:找到具体字体文件 → 用 Path= 精确加载(macOS 主路径)
    font = find_cjk_font(log)
    if font and Path(font["main"]).exists():
        main_dir = font["main"].rsplit("/", 1)[0]
        sans_dir = font["sans"].rsplit("/", 1)[0]
        mono_dir = font["mono"].rsplit("/", 1)[0]
        return (
            "% 中文支持 - xeCJK(按文件路径加载 Noto CJK)\n"
            "\\usepackage{xeCJK}\n"
            f"\\setCJKmainfont{{NotoSerifCJKsc-Regular.otf}}[Path={main_dir}/,Extension=.otf,BoldFont=NotoSerifCJKsc-Bold]\n"
            f"\\setCJKsansfont{{NotoSansCJKsc-Regular.otf}}[Path={sans_dir}/,Extension=.otf,BoldFont=NotoSansCJKsc-Bold]\n"
            f"\\setCJKmonofont{{NotoSansMonoCJKsc-Regular.otf}}[Path={mono_dir}/,Extension=.otf,BoldFont=NotoSansMonoCJKsc-Bold]\n"
            "\\xeCJKsetup{AutoFallBack=true, CJKmath=true}\n"
        )

    # 2) Linux/容器:用 fontconfig 字体族名(fonts-noto-cjk 装的 .ttc 也能被 fc 识别)
    if _has_fontconfig_family("Noto Serif CJK SC") or _has_fontconfig_family("Noto Sans CJK SC"):
        log("🔤 使用 fontconfig 字体名 Noto CJK SC")
        return (
            "% 中文支持 - xeCJK(fontconfig 字体名,Linux/容器)\n"
            "\\usepackage{xeCJK}\n"
            "\\setCJKmainfont{Noto Serif CJK SC}\n"
            "\\setCJKsansfont{Noto Sans CJK SC}\n"
            "\\setCJKmonofont{Noto Sans Mono CJK SC}\n"
            "\\xeCJKsetup{AutoFallBack=true, CJKmath=true}\n"
        )

    # 3) 兜底:按平台选默认字体名
    if platform.system() == "Darwin":
        log("⚠️ 未找到 Noto CJK,回退 macOS 内置字体(正文宋体 Songti SC)")
        return (
            "% 中文支持 - xeCJK(回退 macOS 内置字体:正文宋体)\n"
            "\\usepackage{xeCJK}\n"
            "\\setCJKmainfont{Songti SC}[BoldFont=Songti SC Bold]\n"
            "\\setCJKsansfont{PingFang SC}[BoldFont=PingFang SC Semibold]\n"
            "\\setCJKmonofont{Songti SC}\n"
            "\\xeCJKsetup{AutoFallBack=true, CJKmath=true}\n"
        )
    log("⚠️ 未找到中文字体,回退 Noto CJK 名(需系统已装 fonts-noto-cjk)")
    return (
        "% 中文支持 - xeCJK(回退 Noto CJK 名)\n"
        "\\usepackage{xeCJK}\n"
        "\\setCJKmainfont{Noto Serif CJK SC}\n"
        "\\setCJKsansfont{Noto Sans CJK SC}\n"
        "\\setCJKmonofont{Noto Sans Mono CJK SC}\n"
        "\\xeCJKsetup{AutoFallBack=true, CJKmath=true}\n"
    )



def _ctex_config() -> str:
    return "% 中文支持\n\\usepackage[UTF8]{ctex}\n"


def _read(path: Path) -> tuple[str, str]:
    for enc in ("utf-8", "latin-1", "cp1252", "iso-8859-1"):
        try:
            return path.read_text(encoding=enc), enc
        except (UnicodeDecodeError, UnicodeError):
            continue
    return path.read_bytes().decode("utf-8", errors="replace"), "utf-8"


def _has_active_cjk_package(content: str) -> bool:
    """判断是否已有生效的 xeCJK/ctex 中文支持(忽略被注释的行)。

    注意:原文常自带被注释的 `%\\usepackage{xeCJK}`,若不排除注释行会误判
    "已有中文支持" 而跳过注入,导致 XeLaTeX 下中文无字体、满屏 Missing character。
    另:pdfLaTeX 方案 `CJKutf8` 需要 \\begin{CJK} 环境,在 XeLaTeX 下不算生效,故不计入。
    """
    for line in content.split("\n"):
        stripped = line.lstrip()
        if stripped.startswith("%"):
            continue
        # 去掉行内注释(未转义的 %)后再匹配
        code = re.split(r"(?<!\\)%", line, maxsplit=1)[0]
        if re.search(r"\\usepackage(?:\[[^\]]*\])?\{[^}]*\b(?:xeCJK|ctex)\b[^}]*\}", code):
            return True
    return False


def add_chinese_support(tex_file: Path, log: Logger = print) -> None:
    """在主 tex 的 \\documentclass 之后注入中文支持(幂等)。"""
    content, enc = _read(tex_file)

    if _has_active_cjk_package(content):
        return  # 已有中文支持

    docclass_m = re.search(r"\\documentclass.*?\{([^}]+)\}", content)
    if docclass_m and docclass_m.group(1).strip() not in _STD_DOCCLASSES:
        docclass = docclass_m.group(1).strip()
        log(f"⚠️ 自定义文档类 '{docclass}',使用 xeCJK")
        cls_file = tex_file.parent / f"{docclass}.cls"
        if cls_file.exists():
            fix_cls_for_xelatex(cls_file, log)
        config = _xecjk_config(log)
    else:
        config = _ctex_config()

    lines = content.split("\n")
    out: list[str] = []
    injected = False
    for line in lines:
        out.append(line)
        if not injected and "\\documentclass" in line and not line.strip().startswith("%"):
            injected = True
            out.extend(["", config.strip(), ""])

    tmp = tex_file.with_suffix(".tex.tmp")
    tmp.write_text("\n".join(out), encoding=enc)
    tmp.replace(tex_file)
