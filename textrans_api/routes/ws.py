"""WebSocket 进度推送:/ws/{task_id}。"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..services.task_manager import task_manager

router = APIRouter()


@router.websocket("/ws/{task_id}")
async def ws_progress(websocket: WebSocket, task_id: str) -> None:
    await websocket.accept()

    state = task_manager.get(task_id)
    if state is None:
        await websocket.send_json({"error": "任务不存在"})
        await websocket.close()
        return

    # 先推一次当前快照(避免订阅前已完成的任务看不到状态)
    await websocket.send_json({
        "task_id": state.task_id, "status": state.status, "stage": state.stage,
        "message": state.message, "current": state.current, "total": state.total,
        "error": state.error,
    })
    if state.status in ("done", "failed"):
        await websocket.close()
        return

    queue = task_manager.subscribe(task_id)
    if queue is None:
        await websocket.close()
        return

    try:
        while True:
            event = await queue.get()
            if event.get("_end"):
                break
            await websocket.send_json(event)
    except WebSocketDisconnect:
        pass
    finally:
        task_manager.unsubscribe(task_id, queue)
        try:
            await websocket.close()
        except RuntimeError:
            pass
