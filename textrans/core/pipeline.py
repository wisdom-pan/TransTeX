"""端到端翻译流水线:arXiv → 译文 tex → 中文 PDF → 中英对照 PDF。

编排各 core / llm / latexutil 模块。进度通过 ProgressCallback 上报。
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from ..config import Config, load_config
from ..llm.registry import get_provider
from ..types import ProgressCallback, ProgressEvent, SegmentStats, Stage, TranslateConfig
from . import compile as compile_mod
from .cache import TranslationCache
from .merge import LatexMerger
from .pdf import merge_bilingual
from .split import LatexSplitter
from ..latexutil import arxiv, chinese, watermark


@dataclass
class TranslateResult:
    ok: bool
    workdir: Path
    translated_pdf: Optional[Path] = None
    bilingual_pdf: Optional[Path] = None
    original_pdf: Optional[Path] = None
    main_tex: Optional[Path] = None
    title: Optional[str] = None
    stats: SegmentStats = field(default_factory=SegmentStats)
    message: str = ""


class Pipeline:
    def __init__(
        self,
        tconf: Optional[TranslateConfig] = None,
        config: Optional[Config] = None,
        on_progress: Optional[ProgressCallback] = None,
    ):
        self.tconf = tconf or TranslateConfig()
        self.config = config or load_config()
        self.on_progress = on_progress
        self.provider = get_provider(self.tconf.provider, self.config)
        self.splitter = LatexSplitter(max_token_per_chunk=self.tconf.max_token_per_segment)
        self._glossary: dict = {}

    # ------------------------------------------------------------------ #
    def _build_glossary(self, tex_files, source_dir, cache) -> dict:
        """收集所有文件的待翻译段,生成统一术语表(带缓存)。"""
        import json

        # 缓存命中直接用
        gloss_path = (cache.dir / "glossary.json") if cache is not None else None
        if gloss_path is not None and gloss_path.exists():
            try:
                return json.loads(gloss_path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                pass

        all_segs: List[str] = []
        for tex in tex_files:
            orig = tex.with_suffix(tex.suffix + ".orig")
            content = _read_text(orig) if orig.exists() else _read_text(tex)
            all_segs.extend(self.splitter.split(content).chunks)

        self._emit(Stage.SPLITTING, "生成术语表(统一译名)")
        glossary = self.provider.build_glossary(all_segs, self.tconf.target_lang)
        if glossary:
            self._log(f"📖 术语表 {len(glossary)} 条")
        if gloss_path is not None and glossary:
            try:
                gloss_path.write_text(json.dumps(glossary, ensure_ascii=False), encoding="utf-8")
            except Exception:  # noqa: BLE001
                pass
        return glossary

    # ------------------------------------------------------------------ #
    def _emit(self, stage: Stage, message: str = "", current: int = 0, total: int = 0) -> None:
        if self.on_progress:
            self.on_progress(ProgressEvent(stage=stage, message=message, current=current, total=total))

    def _log(self, msg: str) -> None:
        self._emit(Stage.TRANSLATING, msg)  # 泛用日志走当前阶段
        print(msg)

    # ------------------------------------------------------------------ #
    def run(self, source: str, workdir: Optional[Path] = None) -> TranslateResult:
        """source 可以是 arXiv 链接 / ID,或本地源码目录路径。"""
        base = workdir or (self.config.workdir / _slug(source))
        base.mkdir(parents=True, exist_ok=True)

        # 1) 获取源码
        self._emit(Stage.DOWNLOADING, f"准备源码: {source}")
        try:
            source_dir = self._obtain_source(source, base)
        except Exception as e:  # noqa: BLE001
            return TranslateResult(False, base, message=f"获取源码失败: {e}")

        main_tex = arxiv.find_main_tex(source_dir)
        if main_tex is None:
            return TranslateResult(False, base, message="未找到主 tex 文件")

        stats = SegmentStats()
        cache = TranslationCache(base / "cache") if self.tconf.use_cache else None

        # 2) 逐文件:split → translate → merge → 就地写回
        tex_files = arxiv.collect_tex_files(source_dir)
        self._emit(Stage.SPLITTING, f"发现 {len(tex_files)} 个 tex 文件", 0, len(tex_files))
        main_merger: Optional[LatexMerger] = None
        main_chunks: List[str] = []

        # 2a) 术语表:先扫全文高频术语,统一译法(保证前后一致)
        self._glossary = self._build_glossary(tex_files, source_dir, cache)

        for fi, tex in enumerate(tex_files):
            rel = str(tex.relative_to(source_dir))
            merger, chunks = self._translate_file(tex, rel, cache, stats)
            if tex == main_tex:
                main_merger, main_chunks = merger, chunks
            self._emit(Stage.TRANSLATING, f"已翻译 {rel}", fi + 1, len(tex_files))

        # 3) 注入中文支持(在合并后的主 tex preamble)
        self._emit(Stage.MERGING, "注入中文支持")
        chinese.add_chinese_support(main_tex, self._log)

        # 4) 编译(带日志驱动修复)
        self._emit(Stage.COMPILING, "编译 PDF(含自动修复)")
        if main_merger is not None:
            # 主 tex 走可修复编译(中文支持已注入,需重读合并——见说明)
            pdf = self._compile_main_with_repair(main_tex, main_merger, main_chunks, stats)
        else:
            pdf = None

        if pdf is None:
            return TranslateResult(False, base, main_tex=main_tex, stats=stats, message="编译失败")

        # 5) 收集产物
        out_dir = base / "output"
        out_dir.mkdir(exist_ok=True)
        translated_pdf = out_dir / f"{main_tex.stem}_cn.pdf"
        shutil.copy2(pdf, translated_pdf)

        # 水印(可选)
        if self.tconf.add_watermark and self.tconf.watermark_path:
            wm = out_dir / f"{main_tex.stem}_cn_wm.pdf"
            if watermark.add_watermark(translated_pdf, wm, self.tconf.watermark_path, self._log):
                translated_pdf = wm

        # 6) 中英对照
        bilingual_pdf = None
        original_pdf = None
        if self.tconf.make_bilingual:
            self._emit(Stage.BILINGUAL, "生成中英对照 PDF")
            main_rel = str(main_tex.relative_to(source_dir))
            bilingual_pdf, original_pdf = self._make_bilingual(
                source, base, source_dir, main_rel, translated_pdf, out_dir
            )

        self._emit(Stage.DONE, "完成")
        # 汇总 provider 的 token / API 统计
        stats.input_tokens = self.provider.input_tokens
        stats.output_tokens = self.provider.output_tokens
        stats.api_calls = self.provider.api_calls
        # 提取论文标题(用英文原文,做文件名更稳)
        orig_main = main_tex.with_suffix(main_tex.suffix + ".orig")
        title = arxiv.extract_title(orig_main if orig_main.exists() else main_tex)
        return TranslateResult(
            ok=True, translated_pdf=translated_pdf,
            bilingual_pdf=bilingual_pdf, original_pdf=original_pdf,
            workdir=base, main_tex=main_tex, title=title, stats=stats,
            message="成功",
        )

    # ------------------------------------------------------------------ #
    def _obtain_source(self, source: str, base: Path) -> Path:
        p = Path(source)
        if p.exists() and p.is_dir():
            return p
        arxiv_id = arxiv.extract_arxiv_id(source)
        if not arxiv_id:
            raise ValueError(f"无法识别的 source: {source}")
        tar = arxiv.download_source(arxiv_id, base / "download", self._log)
        return arxiv.extract_source(tar, base / "source", self._log)

    def _translate_file(self, tex: Path, rel: str, cache, stats: SegmentStats):
        # 保留原文副本(.orig),始终从原文分段,使就地写回后重跑仍能命中缓存
        orig_sidecar = tex.with_suffix(tex.suffix + ".orig")
        if orig_sidecar.exists():
            content = _read_text(orig_sidecar)
        else:
            content = _read_text(tex)
            try:
                orig_sidecar.write_text(content, encoding="utf-8")
            except OSError:
                pass  # 只读环境下跳过,不影响首次翻译

        sr = self.splitter.split(content)
        stats.total_segments += len(sr.nodes)
        stats.translated_segments += sr.n_translatable_nodes
        stats.preserved_segments += len(sr.nodes) - sr.n_translatable_nodes

        # 缓存(键=相对路径 + 原文 hash)
        src_hash = cache.content_hash(content) if cache is not None else ""
        chunks: Optional[List[str]] = None
        if cache is not None:
            chunks = cache.load_chunks(rel, len(sr.chunks), src_hash)
        if chunks is None:
            chunks = self.provider.translate_segments(
                sr.chunks,
                target_lang=self.tconf.target_lang,
                max_workers=self.tconf.max_workers,
                on_progress=lambda d, t: self._emit(Stage.TRANSLATING, f"{rel}: {d}/{t} 段", d, t),
                glossary=self._glossary,
            )
            if cache is not None:
                cache.save_chunks(rel, chunks, src_hash)

        merger = LatexMerger(sr)
        merged = merger.merge(chunks, stats=stats)
        tex.write_text(merged, encoding="utf-8")
        return merger, chunks

    def _compile_main_with_repair(self, main_tex, merger, chunks, stats) -> Optional[Path]:
        """主 tex 编译。

        注意:中文支持已被 add_chinese_support 写入文件,而 merger.merge()
        会覆盖文件为纯合并结果(不含中文支持)。为兼顾「日志回退」与「中文支持」,
        这里先记录中文 preamble,再在每次回退合并后重新注入。
        """
        # 简化策略:先普通多轮编译;失败才启用回退(回退时重注入中文支持)。
        engine = "xelatex"
        # 引擎缺失会触发 _run 静默 FileNotFoundError,既不产 .log 也无 PDF,
        # 导致下面回退循环空转,并把无害的「Noto 回退 PingFang」提示当成失败原因。
        # 故先探测一次:缺引擎就直接快速失败,报清楚的根因。
        if not shutil.which(engine):
            self._log(
                f"❌ 未找到 LaTeX 引擎 `{engine}`,无法编译。"
                f"请安装 TeX 发行版(MacTeX/TeX Live)或在 Docker 中运行后端。"
            )
            return None
        ok = compile_mod._compile_passes(main_tex, engine, self._log)
        if ok:
            pdf = main_tex.parent / f"{main_tex.stem}.pdf"
            if pdf.exists() and pdf.stat().st_size > 1000:
                self._log(f"✅ 编译成功: {pdf}")
                return pdf

        # 回退式修复:每轮合并后重注入中文支持再编译
        self._log("⚠️ 首轮编译未成功,启用日志驱动修复")
        log_path = main_tex.parent / f"{main_tex.stem}.log"
        stem = main_tex.stem
        buggy: List[int] = []
        for attempt in range(self.tconf.max_compile_retries):
            radius = 5 * (attempt + 1)
            merged = merger.merge(chunks, buggy_lines=buggy, surgery_radius=radius, stats=stats)
            main_tex.write_text(merged, encoding="utf-8")
            chinese.add_chinese_support(main_tex, self._log)
            if compile_mod._compile_passes(main_tex, engine, self._log):
                pdf = main_tex.parent / f"{stem}.pdf"
                if pdf.exists() and pdf.stat().st_size > 1000:
                    self._log(f"✅ 修复后编译成功(第 {attempt+1} 轮)")
                    return pdf
            new_buggy = compile_mod.extract_buggy_lines(log_path, stem)
            if not new_buggy or set(new_buggy).issubset(set(buggy)):
                break
            buggy = sorted(set(buggy) | set(new_buggy))
        return None

    def _make_bilingual(self, source, base, source_dir, main_rel, translated_pdf, out_dir):
        """编译原文 PDF 并与译文拼接成对照 PDF。

        返回 (bilingual_pdf, original_pdf);任一失败则对应项为 None。
        原文 PDF 也单独复制到 output/,供前端做中英并排预览。
        原文来自翻译时保留的 .orig 边车副本(适用于 arXiv 与本地/上传源),
        复制整个源目录到 orig_build/,把每个 .tex.orig 还原为 .tex 后编译。
        """
        import shutil

        try:
            orig_build = base / "orig_build"
            if orig_build.exists():
                shutil.rmtree(orig_build)
            shutil.copytree(source_dir, orig_build)

            # 用 .orig 覆盖被翻译写回的 .tex,恢复英文原文
            restored = 0
            for orig_file in orig_build.rglob("*.tex.orig"):
                target = orig_file.with_suffix("")  # 去掉 .orig
                shutil.copy2(orig_file, target)
                orig_file.unlink(missing_ok=True)
                restored += 1
            if restored == 0:
                self._log("⚠️ 无 .orig 原文副本,跳过对照 PDF")
                return None, None

            orig_main = orig_build / main_rel
            if not orig_main.exists():
                orig_main = arxiv.find_main_tex(orig_build)
            if orig_main is None:
                self._log("⚠️ 原文主 tex 未找到,跳过对照")
                return None, None

            # 原文用 pdflatex,不行再 xelatex
            if not compile_mod._compile_passes(orig_main, "pdflatex", self._log):
                compile_mod._compile_passes(orig_main, "xelatex", self._log)
            orig_pdf = orig_main.parent / f"{orig_main.stem}.pdf"
            if not orig_pdf.exists() or orig_pdf.stat().st_size < 1000:
                self._log("⚠️ 原文 PDF 编译失败,跳过对照")
                return None, None

            # 原文 PDF 收集为产物(供并排预览/下载)
            original_out = out_dir / f"{orig_main.stem}_orig.pdf"
            shutil.copy2(orig_pdf, original_out)

            out = out_dir / f"{orig_main.stem}_bilingual.pdf"
            bilingual = merge_bilingual(orig_pdf, translated_pdf, out, self._log)
            return bilingual, original_out
        except Exception as e:  # noqa: BLE001
            self._log(f"⚠️ 对照 PDF 生成异常: {e}")
            return None, None


def _read_text(path: Path) -> str:
    for enc in ("utf-8", "latin-1", "cp1252", "iso-8859-1"):
        try:
            return path.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
    return path.read_bytes().decode("utf-8", errors="replace")


def _slug(source: str) -> str:
    aid = arxiv.extract_arxiv_id(source)
    if aid:
        return aid
    return Path(source).name or "task"
