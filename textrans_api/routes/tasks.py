"""任务相关 REST 接口。"""
from __future__ import annotations

import re
import shutil
import tempfile
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from ..schemas import CreateTaskRequest, CreateTaskResponse, TaskArtifacts, TaskStatus
from ..services.task_manager import TaskState, task_manager

router = APIRouter(prefix="/api", tags=["tasks"])

# 上传源码的解压根目录
_UPLOAD_ROOT = Path(tempfile.gettempdir()) / "textrans_uploads"


def _to_status(state: TaskState) -> TaskStatus:
    return TaskStatus(
        task_id=state.task_id,
        status=state.status,
        stage=state.stage,
        message=state.message,
        progress_current=state.current,
        progress_total=state.total,
        error=state.error,
        artifacts=TaskArtifacts(
            translated_pdf=(f"/api/tasks/{state.task_id}/download/translated"
                            if state.translated_pdf else None),
            bilingual_pdf=(f"/api/tasks/{state.task_id}/download/bilingual"
                           if state.bilingual_pdf else None),
            original_pdf=(f"/api/tasks/{state.task_id}/download/original"
                          if state.original_pdf else None),
        ),
        title=state.title,
        source=state.source,
        created_at=state.created_at,
    )


@router.post("/tasks", response_model=CreateTaskResponse)
def create_task(req: CreateTaskRequest) -> CreateTaskResponse:
    """通过 arXiv 链接/ID 创建翻译任务。"""
    if not req.arxiv_url:
        raise HTTPException(400, "arxiv_url 不能为空")
    task_id = task_manager.create_task(
        req.arxiv_url, provider=req.provider,
        make_bilingual=req.make_bilingual, workers=req.workers,
    )
    return CreateTaskResponse(task_id=task_id, status="queued")


@router.post("/tasks/upload", response_model=CreateTaskResponse)
async def create_task_upload(
    file: UploadFile = File(...),
    provider: Optional[str] = Form(None),
    make_bilingual: bool = Form(True),
    workers: int = Form(8),
) -> CreateTaskResponse:
    """上传 tex 源码压缩包(.zip/.tar.gz)创建任务。"""
    import tarfile
    import zipfile

    _UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    dest = _UPLOAD_ROOT / Path(file.filename or "upload").stem
    dest.mkdir(parents=True, exist_ok=True)

    raw = dest.parent / (file.filename or "upload.bin")
    with open(raw, "wb") as f:
        shutil.copyfileobj(file.file, f)

    try:
        if zipfile.is_zipfile(raw):
            with zipfile.ZipFile(raw) as z:
                z.extractall(dest)
        elif tarfile.is_tarfile(raw):
            with tarfile.open(raw) as t:
                t.extractall(dest)
        else:
            raise HTTPException(400, "仅支持 .zip / .tar.gz")
    finally:
        raw.unlink(missing_ok=True)

    # 若解压出单一子目录,以其为源
    entries = [p for p in dest.iterdir()]
    source_dir = entries[0] if len(entries) == 1 and entries[0].is_dir() else dest

    task_id = task_manager.create_task(
        str(source_dir), provider=provider,
        make_bilingual=make_bilingual, workers=workers,
    )
    return CreateTaskResponse(task_id=task_id, status="queued")


@router.get("/tasks", response_model=List[TaskStatus])
def list_tasks() -> List[TaskStatus]:
    return [_to_status(s) for s in task_manager.all()]


@router.get("/tasks/{task_id}", response_model=TaskStatus)
def get_task(task_id: str) -> TaskStatus:
    state = task_manager.get(task_id)
    if state is None:
        raise HTTPException(404, "任务不存在")
    return _to_status(state)


@router.get("/tasks/{task_id}/download/{kind}")
def download(task_id: str, kind: str, inline: bool = False) -> FileResponse:
    state = task_manager.get(task_id)
    if state is None:
        raise HTTPException(404, "任务不存在")
    path: Optional[Path]
    if kind == "translated":
        path = state.translated_pdf
    elif kind == "bilingual":
        path = state.bilingual_pdf
    elif kind == "original":
        path = state.original_pdf
    else:
        raise HTTPException(400, "kind 须为 translated | bilingual | original")
    if not path or not path.exists():
        raise HTTPException(404, f"{kind} PDF 尚不可用")
    # inline=预览(浏览器内渲染),否则=下载(带论文标题文件名)
    if inline:
        return FileResponse(
            str(path), media_type="application/pdf",
            headers={"Content-Disposition": "inline"},
        )
    filename = _download_filename(state.title, kind, path)
    return FileResponse(str(path), media_type="application/pdf", filename=filename)


def _download_filename(title: Optional[str], kind: str, path: Path) -> str:
    """用论文标题生成下载文件名;无标题则回退原文件名。"""
    if not title:
        return path.name
    # 清洗成合法文件名:去掉非法字符,限长
    safe = re.sub(r'[\\/:*?"<>|]', " ", title)
    safe = re.sub(r"\s+", " ", safe).strip()[:120].strip()
    if not safe:
        return path.name
    suffix = {"bilingual": "_中英对照", "original": "_原文"}.get(kind, "_中文")
    return f"{safe}{suffix}.pdf"
