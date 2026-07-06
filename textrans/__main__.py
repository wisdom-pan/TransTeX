"""命令行入口:python -m textrans <arxiv_id|url|dir> [选项]"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import load_config
from .core.pipeline import Pipeline
from .types import ProgressEvent, Stage, TranslateConfig


def _progress(ev: ProgressEvent) -> None:
    bar = ""
    if ev.total:
        bar = f" [{ev.current}/{ev.total}]"
    print(f"  ▸ {ev.stage.value}{bar} {ev.message}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="textrans",
        description="LaTeX 论文翻译(掩码内核):arXiv → 中文 PDF + 中英对照",
    )
    parser.add_argument("source", help="arXiv 链接 / ID,或本地源码目录")
    parser.add_argument("--provider", default=None, help="LLM provider(kimi/openai)")
    parser.add_argument("--workers", type=int, default=8, help="并发翻译线程数")
    parser.add_argument("--workdir", default=None, help="工作目录")
    parser.add_argument("--lang", default="简体中文", help="目标语言")
    parser.add_argument("--no-bilingual", action="store_true", help="不生成中英对照 PDF")
    parser.add_argument("--no-cache", action="store_true", help="禁用断点续传缓存")
    parser.add_argument("--watermark", default=None, help="水印图片路径(默认用项目内 dt.l.png)")
    parser.add_argument("--no-watermark", action="store_true", help="不添加水印")
    parser.add_argument("--debug-mask", action="store_true", help="导出掩码可视化 HTML 后退出(不翻译)")
    args = parser.parse_args(argv)

    config = load_config()

    if args.debug_mask:
        return _debug_mask(args, config)

    wm_path = Path(args.watermark) if args.watermark else config.watermark_path
    use_wm = not args.no_watermark and wm_path.exists()

    tconf = TranslateConfig(
        provider=args.provider or config.default_provider,
        max_workers=args.workers,
        target_lang=args.lang,
        make_bilingual=not args.no_bilingual,
        use_cache=not args.no_cache,
        add_watermark=use_wm,
        watermark_path=wm_path if use_wm else None,
    )

    pipeline = Pipeline(tconf=tconf, config=config, on_progress=_progress)
    workdir = Path(args.workdir) if args.workdir else None
    result = pipeline.run(args.source, workdir=workdir)

    print("\n" + "=" * 60)
    if result.ok:
        print("✅ 翻译完成")
        print(f"   译文 PDF:   {result.translated_pdf}")
        if result.bilingual_pdf:
            print(f"   对照 PDF:   {result.bilingual_pdf}")
    else:
        print(f"❌ 失败: {result.message}")
    s = result.stats
    print(f"   段落: 总 {s.total_segments} / 翻译 {s.translated_segments} / 保护 {s.preserved_segments}")
    print(f"   编译回退段: {s.reverted_on_compile}")
    print(f"   token: 入 {s.input_tokens} / 出 {s.output_tokens} / API {s.api_calls} 次")
    print("=" * 60)
    return 0 if result.ok else 1


def _debug_mask(args, config) -> int:
    """仅导出掩码可视化,便于人工核对保护规则。"""
    from .core.split import LatexSplitter
    from .latexutil import arxiv

    src = Path(args.source)
    if src.is_dir():
        main_tex = arxiv.find_main_tex(src)
    elif src.is_file():
        main_tex = src
    else:
        print("--debug-mask 需要本地目录或 tex 文件")
        return 1
    if main_tex is None:
        print("未找到主 tex")
        return 1

    content = main_tex.read_text(encoding="utf-8", errors="replace")
    sr = LatexSplitter().split(content)
    out = main_tex.parent / "debug_mask.html"
    out.write_text(sr.debug_html(), encoding="utf-8")
    print(f"掩码可视化已导出: {out}")
    print(f"节点 {len(sr.nodes)},待翻译 {sr.n_translatable_nodes},chunks {len(sr.chunks)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
