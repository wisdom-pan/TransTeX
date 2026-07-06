"""TexTrans FastAPI 应用入口。

启动:uvicorn textrans_api.main:app --reload --port 8000
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes import tasks, ws
from .services.task_manager import task_manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 让 TaskManager 能跨线程向事件循环投递进度
    task_manager.bind_loop(asyncio.get_running_loop())
    yield


app = FastAPI(title="TexTrans API", version="0.1.0", lifespan=lifespan)

# 开发期允许 Next.js(localhost:5000)跨域;生产建议用 next.config rewrites 代理
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5000", "http://127.0.0.1:5000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tasks.router)
app.include_router(ws.router)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "service": "textrans-api"}
