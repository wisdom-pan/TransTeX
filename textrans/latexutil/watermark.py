"""给 PDF 每页左上角加图片水印(pypdf + reportlab)。

从旧 main.py 的 add_watermark 迁移。
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Callable, Optional

Logger = Callable[[str], None]


def add_watermark(pdf_path: Path, output_path: Path, watermark_img: Path, log: Logger = print) -> Optional[Path]:
    """在每页左上角叠加水印图片。失败返回 None。"""
    try:
        from pypdf import PdfReader, PdfWriter
        from reportlab.pdfgen import canvas
        from PIL import Image
    except ImportError as e:
        log(f"⚠️ 缺少水印依赖: {e}")
        return None

    if not watermark_img.exists():
        log(f"⚠️ 水印图片不存在: {watermark_img}")
        return None

    try:
        reader = PdfReader(str(pdf_path))
        writer = PdfWriter()

        img_w, img_h = Image.open(str(watermark_img)).size
        scale = 0.15
        base_w, base_h = img_w * scale, img_h * scale

        for page in reader.pages:
            pw = float(page.mediabox.width)
            ph = float(page.mediabox.height)

            max_w = pw - 20
            if base_w > max_w:
                s = max_w / base_w
                wm_w, wm_h = max_w, base_h * s
            else:
                wm_w, wm_h = base_w, base_h

            packet = BytesIO()
            c = canvas.Canvas(packet, pagesize=(pw, ph))
            c.drawImage(
                str(watermark_img),
                10, ph - wm_h - 10,
                width=wm_w, height=wm_h,
                preserveAspectRatio=True, mask="auto",
            )
            c.save()
            packet.seek(0)

            page.merge_page(PdfReader(packet).pages[0])
            writer.add_page(page)

        with open(output_path, "wb") as f:
            writer.write(f)
        log(f"✅ 水印添加完成: {output_path}")
        return output_path
    except Exception as e:  # noqa: BLE001
        log(f"❌ 水印添加失败: {e}")
        return None
