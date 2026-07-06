"""中英对照 PDF:把原文 PDF 与译文 PDF 左右双栏拼接。

每一页新建一个宽度 = 左页宽 + 右页宽的画布,左贴原文、右贴译文。
算法思想借鉴 gpt_academic 的 merge_pdfs,用较新的 pypdf API clean-room 实现。
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

Logger = Callable[[str], None]


def merge_bilingual(orig_pdf: Path, trans_pdf: Path, out_pdf: Path, log: Logger = print) -> Optional[Path]:
    """生成左原文 / 右译文的对照 PDF。失败返回 None。"""
    try:
        from pypdf import PdfReader, PdfWriter, Transformation
        from pypdf.generic import RectangleObject
    except ImportError as e:
        log(f"⚠️ 缺少 pypdf: {e}")
        return None

    try:
        r_orig = PdfReader(str(orig_pdf))
        r_trans = PdfReader(str(trans_pdf))
        writer = PdfWriter()

        n = max(len(r_orig.pages), len(r_trans.pages))
        for i in range(n):
            left = r_orig.pages[i] if i < len(r_orig.pages) else None
            right = r_trans.pages[i] if i < len(r_trans.pages) else None

            lw = float(left.mediabox.width) if left else 0.0
            lh = float(left.mediabox.height) if left else 0.0
            rw = float(right.mediabox.width) if right else 0.0
            rh = float(right.mediabox.height) if right else 0.0

            new_w = lw + rw
            new_h = max(lh, rh)
            if new_w == 0 or new_h == 0:
                continue

            blank = writer.add_blank_page(width=new_w, height=new_h)
            if left is not None:
                blank.merge_page(left)  # 左栏,原点在左下,x=0
            if right is not None:
                # 右栏:整体右移左页宽度
                blank.merge_transformed_page(right, Transformation().translate(tx=lw, ty=0))

        with open(out_pdf, "wb") as f:
            writer.write(f)
        log(f"✅ 对照 PDF 生成: {out_pdf}")
        return out_pdf
    except Exception as e:  # noqa: BLE001
        log(f"❌ 对照 PDF 生成失败: {e}")
        return None
