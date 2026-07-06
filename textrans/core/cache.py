"""断点续传缓存:把翻译中间结果存成 JSON,重跑时跳过已完成阶段。

只缓存纯字符串数组(译文 chunks)与元信息,不序列化对象,
从而避免 gpt_academic 的 pickle 安全问题,且跨版本稳定。

缓存键 = 文件相对路径;同时校验原文内容 hash,原文变化则自动失效。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import List, Optional


class TranslationCache:
    def __init__(self, cache_dir: Path):
        self.dir = cache_dir
        self.dir.mkdir(parents=True, exist_ok=True)

    def _key(self, tex_rel: str) -> str:
        return hashlib.md5(tex_rel.encode("utf-8")).hexdigest()[:16]

    def _chunk_path(self, tex_rel: str) -> Path:
        return self.dir / f"{self._key(tex_rel)}.chunks.json"

    @staticmethod
    def content_hash(content: str) -> str:
        return hashlib.md5(content.encode("utf-8")).hexdigest()

    def load_chunks(self, tex_rel: str, expected_n: int, src_hash: str) -> Optional[List[str]]:
        """载入翻译结果;chunk 数不符或原文 hash 不符则视为失效。"""
        p = self._chunk_path(tex_rel)
        if not p.exists():
            return None
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        if data.get("src_hash") != src_hash:
            return None  # 原文已变,缓存失效
        chunks = data.get("chunks")
        if not isinstance(chunks, list) or len(chunks) != expected_n:
            return None
        return chunks

    def save_chunks(self, tex_rel: str, chunks: List[str], src_hash: str) -> None:
        p = self._chunk_path(tex_rel)
        p.write_text(
            json.dumps(
                {"tex": tex_rel, "src_hash": src_hash, "chunks": chunks},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def clear(self, tex_rel: Optional[str] = None) -> None:
        if tex_rel is None:
            for f in self.dir.glob("*.chunks.json"):
                f.unlink(missing_ok=True)
        else:
            self._chunk_path(tex_rel).unlink(missing_ok=True)
