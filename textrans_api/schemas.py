"""Pydantic 请求/响应模型。"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class CreateTaskRequest(BaseModel):
    """通过 arXiv 链接/ID 创建任务(上传 zip 走 multipart,不用此模型)。"""

    type: str = Field(default="arxiv", description="arxiv | upload")
    arxiv_url: Optional[str] = Field(default=None, description="arXiv 链接或 ID")
    provider: Optional[str] = Field(default=None, description="LLM provider(kimi/openai)")
    make_bilingual: bool = True
    workers: int = 8


class TaskArtifacts(BaseModel):
    translated_pdf: Optional[str] = None
    bilingual_pdf: Optional[str] = None
    original_pdf: Optional[str] = None


class TaskStatus(BaseModel):
    task_id: str
    status: str  # queued | running | done | failed
    stage: str = "queued"
    message: str = ""
    progress_current: int = 0
    progress_total: int = 0
    artifacts: TaskArtifacts = Field(default_factory=TaskArtifacts)
    error: Optional[str] = None
    title: Optional[str] = None
    source: Optional[str] = None
    created_at: Optional[float] = None


class CreateTaskResponse(BaseModel):
    task_id: str
    status: str


class ReloadResponse(BaseModel):
    changed: int = Field(description="本次刷新中状态/产物发生变更的任务数")
    total: int = Field(description="刷新后内存中的任务总数")
