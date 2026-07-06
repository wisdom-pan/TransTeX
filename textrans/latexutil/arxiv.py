"""arXiv 源码下载 / 解压 / 主 tex 定位。

从旧 main.py 的 ArxivDownloader + find_main_tex 迁移(本项目原创,非 GPL)。
"""
from __future__ import annotations

import re
import tarfile
from pathlib import Path
from typing import Callable, List, Optional

import requests

Logger = Callable[[str], None]

_ID_PATTERNS = [
    r"arxiv\.org/abs/(\d+\.\d+)(?:v\d+)?",
    r"arxiv\.org/abs/(\d+)(?:v\d+)?",
    r"arxiv\.org/pdf/(\d+\.\d+)(?:v\d+)?",
    r"arxiv\.org/pdf/(\d+)(?:v\d+)?",
    r"arXiv:(\d+\.\d+)(?:v\d+)?",
    r"arXiv:(\d+)(?:v\d+)?",
    r"^(\d+\.\d+)(?:v\d+)?$",
    r"^(\d{4}\.\d{4,5})(?:v\d+)?$",
]


def extract_arxiv_id(url: str) -> Optional[str]:
    """从链接 / 纯 ID 中提取 arXiv ID(去掉版本号)。"""
    for pat in _ID_PATTERNS:
        m = re.search(pat, url.strip())
        if m:
            return re.sub(r"v\d+$", "", m.group(1))
    return None


def download_source(arxiv_id: str, output_dir: Path, log: Logger = print) -> Path:
    """下载 arXiv e-print 源码包(.tar.gz);已存在且有效则复用。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    tar_path = output_dir / f"{arxiv_id}.tar.gz"

    if tar_path.exists():
        try:
            with tarfile.open(tar_path, "r:gz") as tar:
                tar.getmembers()
            log(f"📦 使用已下载源码: {tar_path}")
            return tar_path
        except (tarfile.TarError, EOFError):
            log("⚠️ 已下载文件无效,重新下载")
            tar_path.unlink(missing_ok=True)

    url = f"https://arxiv.org/e-print/{arxiv_id}"
    log(f"📥 下载论文源码: {arxiv_id}")
    resp = requests.get(url, stream=True, timeout=120)
    resp.raise_for_status()

    ct = resp.headers.get("content-type", "")
    cl = int(resp.headers.get("content-length", 0))
    if "text/html" in ct and cl < 10000:
        raise ValueError(f"arXiv 返回 HTML,论文可能不存在: {arxiv_id}")

    with open(tar_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)

    try:
        with tarfile.open(tar_path, "r:gz") as tar:
            if not tar.getmembers():
                raise ValueError("下载的 tar.gz 为空")
    except tarfile.TarError:
        raise ValueError(f"下载文件不是有效 tar.gz(可能只有 PDF): {arxiv_id}")

    log(f"✅ 下载完成: {tar_path}")
    return tar_path


def extract_source(tar_path: Path, extract_dir: Path, log: Logger = print) -> Path:
    """解压源码包,返回包含 main.tex 的目录。"""
    if extract_dir.exists():
        found = _find_dir_with_main(extract_dir)
        if found:
            log(f"📂 使用已解压源码: {found}")
            return found

    log("📦 解压源码...")
    extract_dir.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tar_path, "r:gz") as tar:
        tar.extractall(extract_dir)

    found = _find_dir_with_main(extract_dir)
    src = found or extract_dir
    log(f"✅ 解压完成: {src}")
    return src


def _find_dir_with_main(root: Path) -> Optional[Path]:
    if (root / "main.tex").exists():
        return root
    for item in root.iterdir():
        if item.is_dir() and (item / "main.tex").exists():
            return item
    return None


def _read_tex(path: Path) -> str:
    for enc in ("utf-8", "latin-1", "cp1252", "iso-8859-1"):
        try:
            return path.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
    return path.read_bytes().decode("utf-8", errors="replace")


def collect_tex_files(source_dir: Path) -> List[Path]:
    """收集所有 .tex 文件(排除已翻译产物目录)。"""
    return sorted(
        p for p in source_dir.rglob("*.tex") if "paper_cn" not in str(p)
    )


def find_main_tex(source_dir: Path) -> Optional[Path]:
    """启发式定位主 tex 文件(含 \\begin{document} 且评分最高)。"""
    candidates = []
    for tex in source_dir.rglob("*.tex"):
        if "paper_cn" in tex.parts:  # 跳过译文产物目录
            continue
        content = _read_tex(tex)
        if r"\begin{document}" not in content:
            continue
        score = 0
        if r"\documentclass" in content:
            score += 10
        if r"\title" in content or r"\author" in content:
            score += 5
        if "main" in tex.name.lower():
            score += 3
        candidates.append((score, tex))
    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]
    return None


def extract_title(tex_file: Path) -> Optional[str]:
    r"""从 tex 里提取论文标题纯文本(去掉 \title{} 及内部 LaTeX 命令)。

    会尝试展开标题里的自定义系统名宏(如 \sys → TurboServe)。
    用于给下载文件命名。失败返回 None。
    """
    content = _read_tex(tex_file)
    macros = _collect_simple_macros(content)
    # 只看未注释的 \title(跳过以 % 开头的行)
    for m in re.finditer(r"^[^%\n]*?\\title\s*(?:\[[^\]]*\])?\s*\{", content, re.MULTILINE):
        brace = content.find("{", m.end() - 1)
        if brace == -1:
            continue
        # 配平花括号取整个 \title{...}
        depth, i = 0, brace
        while i < len(content):
            c = content[i]
            if c == "\\":
                i += 2
                continue
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        raw = content[brace + 1:i]
        # 先展开系统名宏,再清洗
        for name, val in macros.items():
            raw = raw.replace("\\" + name + "{}", val).replace("\\" + name + " ", val + " ")
            raw = re.sub(r"\\" + re.escape(name) + r"\b", val, raw)
        title = _strip_latex(raw)
        if title:
            return title
    return None


def _collect_simple_macros(content: str) -> Dict[str, str]:
    r"""收集无参简单宏 \newcommand{\x}{...},展开成纯文本(用于标题里的系统名)。"""
    macros: Dict[str, str] = {}
    for m in re.finditer(r"\\newcommand\s*\{?\\([a-zA-Z]+)\}?\s*\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}", content):
        name, body = m.group(1), m.group(2)
        text = _strip_latex(body)
        if text and len(text) <= 40:
            macros[name] = text
    return macros


def _strip_latex(s: str) -> str:
    """去掉 LaTeX 命令/花括号/多余空白,得到可读纯文本。"""
    s = re.sub(r"\\(?:thanks|footnote|label)\{[^}]*\}", "", s)  # 丢弃这些命令及内容
    s = re.sub(r"\\\\(?:\[[^\]]*\])?", " ", s)                   # 换行 → 空格
    s = re.sub(r"\\[a-zA-Z]+\*?", "", s)                          # 其余命令名删掉,保留其花括号内文字
    s = s.replace("{", "").replace("}", "")
    s = re.sub(r"\$[^$]*\$", "", s)                               # 丢弃行内公式
    s = re.sub(r"\s+", " ", s).strip()
    s = s.lstrip(":：-—　 ").strip()                              # 去掉宏展开失败残留的前导标点
    return s


