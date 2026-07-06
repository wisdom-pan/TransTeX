'use client'

import { useEffect, useRef, useState } from 'react'
import { getTask, TaskStatus } from './api'

export interface ProgressState {
  status: string
  stage: string
  message: string
  current: number
  total: number
  error: string | null
}

const INITIAL: ProgressState = {
  status: 'queued',
  stage: 'queued',
  message: '',
  current: 0,
  total: 0,
  error: null,
}

// 订阅任务进度:优先 WebSocket,结束时再拉一次完整状态(取 artifacts)。
export function useTaskSocket(taskId: string | null) {
  const [progress, setProgress] = useState<ProgressState>(INITIAL)
  const [finalStatus, setFinalStatus] = useState<TaskStatus | null>(null)
  const wsRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    if (!taskId) return
    setProgress(INITIAL)
    setFinalStatus(null)

    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${proto}://${window.location.host}/ws/${taskId}`)
    wsRef.current = ws

    const fetchFinal = async () => {
      try {
        const s = await getTask(taskId)
        setFinalStatus(s)
        setProgress((p) => ({ ...p, status: s.status, stage: s.stage, error: s.error }))
      } catch {
        /* ignore */
      }
    }

    ws.onmessage = (ev) => {
      const d = JSON.parse(ev.data)
      if (d.error) {
        setProgress((p) => ({ ...p, error: d.error }))
        return
      }
      setProgress({
        status: d.status ?? 'running',
        stage: d.stage ?? 'running',
        message: d.message ?? '',
        current: d.current ?? 0,
        total: d.total ?? 0,
        error: d.error ?? null,
      })
      if (d.status === 'done' || d.status === 'failed') {
        void fetchFinal()
      }
    }

    ws.onclose = () => {
      // WS 关闭(任务结束或断连)时兜底拉一次
      void fetchFinal()
    }
    ws.onerror = () => {
      void fetchFinal()
    }

    return () => {
      wsRef.current = null
      ws.close()
    }
  }, [taskId])

  return { progress, finalStatus }
}
