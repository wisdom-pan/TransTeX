"""外科式重译:只重译缓存里「仍是英文/空」的 chunk,不动其余已译内容。

背景:prompt 规则曾把句子碎片(被 \\cite/\\ref/公式从中间截断的半句)误判为
"无需翻译"而原样返回英文。修好 prompt 后,已缓存的英文 chunk 不会自动重译
(缓存按整文件 + 原文 hash 命中)。本脚本挑出这些 chunk 定点重译,更新缓存,
并用 LatexMerger 重新合并写回 .tex。约几十次 API 调用,成本低。

用法:
    python3 scripts/retranslate_untranslated_chunks.py [--dry-run] [--workdir DIR] [ID ...]

不带 ID 则处理 workdir 下全部论文。--dry-run 只报告不改动、不调 API。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# 允许从项目根直接运行
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from textrans.config import load_config  # noqa: E402
from textrans.core.split import LatexSplitter  # noqa: E402
from textrans.core.merge import LatexMerger  # noqa: E402
from textrans.llm.registry import get_provider  # noqa: E402
from textrans.llm.glossary import format_glossary  # noqa: E402
from textrans.llm.prompts import build_system_prompt  # noqa: E402

CJK = re.compile(r"[一-鿿]")
LATIN = re.compile(r"[A-Za-z]")


def needs_retranslation(src: str, tr: str | None) -> bool:
    """源含实质英文词句,但译文无中文(原样英文或空)→ 需重译。

    排除:纯 LaTeX 代码块(多命令、无句末标点),这类原样保留正确。
    """
    s = src.strip()
    if len(s) < 40:
        return False
    if len(LATIN.findall(s)) <= 15:
        return False  # 英文太少,可能是符号/编号
    if CJK.search(tr or ""):
        return False  # 已翻译
    # 纯 LaTeX 代码块(如 \setlength/\hypersetup 堆叠):命令多、无自然句
    if s.startswith("\\") and s.count("\\") > 3 and not re.search(r"[.!?]\s", s):
        return False
    return True


def process_paper(paper: Path, provider, splitter, dry_run: bool) -> tuple[int, int]:
    """返回 (重译chunk数, 重写文件数)。"""
    cache_dir = paper / "cache"
    if not cache_dir.exists():
        return 0, 0

    # 复用统一术语表(与首次翻译一致)
    glossary = {}
    gp = cache_dir / "glossary.json"
    if gp.exists():
        try:
            glossary = json.loads(gp.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            glossary = {}
    system_prompt = build_system_prompt("简体中文")
    if glossary:
        system_prompt += format_glossary(glossary)

    n_chunks = 0
    n_files = 0
    for cf in sorted(cache_dir.glob("*.chunks.json")):
        try:
            data = json.loads(cf.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        rel = data.get("tex")
        chunks = data.get("chunks")
        if not rel or not isinstance(chunks, list):
            continue

        of = paper / "source" / (rel + ".orig")
        texf = paper / "source" / rel
        if not of.exists() or not texf.exists():
            continue

        orig = of.read_text(encoding="utf-8", errors="replace")
        sr = splitter.split(orig)
        if len(sr.chunks) != len(chunks):
            print(f"    ! 跳过(缓存chunk数不符,需整篇重跑): {rel}")
            continue

        # 定位需重译的 chunk 下标
        targets = [i for i, (s, t) in enumerate(zip(sr.chunks, chunks))
                   if needs_retranslation(s, t)]
        if not targets:
            continue

        print(f"    {rel}: {len(targets)} 个碎片待重译")
        if not dry_run:
            for i in targets:
                new_tr = provider._translate_with_retry(sr.chunks[i], system_prompt)
                chunks[i] = new_tr
            # 写回缓存(src_hash 不变,保持整文件缓存有效)
            data["chunks"] = chunks
            cf.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            # 重新合并写回 .tex
            merged = LatexMerger(sr).merge(chunks)
            texf.write_text(merged, encoding="utf-8")
            n_files += 1
        n_chunks += len(targets)

    return n_chunks, n_files


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="外科重译缓存中残留的英文碎片")
    ap.add_argument("ids", nargs="*", help="论文 ID(留空=全部)")
    ap.add_argument("--workdir", default=None, help="工作目录(默认取配置)")
    ap.add_argument("--dry-run", action="store_true", help="只报告不改动、不调 API")
    args = ap.parse_args(argv)

    config = load_config()
    workdir = Path(args.workdir) if args.workdir else config.workdir
    if not workdir.exists():
        print(f"工作目录不存在: {workdir}")
        return 1

    provider = None if args.dry_run else get_provider(config.default_provider, config)
    splitter = LatexSplitter()

    if args.ids:
        papers = [workdir / i for i in args.ids]
    else:
        papers = [p for p in sorted(workdir.iterdir()) if p.is_dir() and (p / "cache").exists()]

    total_chunks = 0
    total_files = 0
    for paper in papers:
        if not paper.is_dir():
            print(f"跳过(不存在): {paper.name}")
            continue
        print(f"[{paper.name}]")
        c, f = process_paper(paper, provider, splitter, args.dry_run)
        total_chunks += c
        total_files += f

    verb = "待重译" if args.dry_run else "已重译"
    print(f"\n{'='*50}\n{verb} chunk: {total_chunks}  重写文件: {total_files}")
    if args.dry_run:
        print("(dry-run:未调用 API、未改动文件)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
