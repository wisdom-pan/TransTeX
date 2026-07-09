'use client'

import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { ArrowLeft, FileText, Clock, CheckCircle2, XCircle, Loader2, Inbox, RefreshCw } from 'lucide-react'
import Navbar from '@/components/Navbar'
import { listTasks, reloadTasks, TaskStatus } from '@/lib/api'

const STATUS_META: Record<
  string,
  { label: string; icon: React.ReactNode; cls: string }
> = {
  done: { label: '已完成', icon: <CheckCircle2 className="w-4 h-4" />, cls: 'text-green-600 bg-green-50' },
  failed: { label: '失败', icon: <XCircle className="w-4 h-4" />, cls: 'text-red-500 bg-red-50' },
  running: { label: '进行中', icon: <Loader2 className="w-4 h-4 animate-spin" />, cls: 'text-violet-600 bg-violet-50' },
  queued: { label: '排队中', icon: <Clock className="w-4 h-4" />, cls: 'text-amber-600 bg-amber-50' },
}

function fmtTime(ts?: number | null): string {
  if (!ts) return ''
  const d = new Date(ts * 1000)
  return d.toLocaleString('zh-CN', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit',
  })
}

export default function HistoryPage() {
  const [tasks, setTasks] = useState<TaskStatus[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)

  const fetchTasks = useCallback(async () => {
    const list = await listTasks()
    // 按创建时间倒序(新的在前);无 created_at 的排后面
    setTasks([...list].sort((a, b) => (b.created_at ?? 0) - (a.created_at ?? 0)))
  }, [])

  useEffect(() => {
    let active = true
    listTasks()
      .then((list) => {
        if (!active) return
        setTasks([...list].sort((a, b) => (b.created_at ?? 0) - (a.created_at ?? 0)))
      })
      .catch((e) => active && setError(e instanceof Error ? e.message : '加载失败'))
    return () => {
      active = false
    }
  }, [])

  // 重扫磁盘同步后端(CLI 重跑后刷新对照/原文 PDF),再重新拉取列表
  const handleRefresh = useCallback(async () => {
    setRefreshing(true)
    setError(null)
    try {
      await reloadTasks()
      await fetchTasks()
    } catch (e) {
      setError(e instanceof Error ? e.message : '刷新失败')
    } finally {
      setRefreshing(false)
    }
  }, [fetchTasks])

  return (
    <main className="min-h-screen bg-gradient-to-b from-slate-50 to-white">
      <Navbar />
      <div className="container mx-auto px-4 pt-8 pb-16 max-w-3xl">
        <Link
          href="/"
          className="inline-flex items-center gap-1 text-sm text-gray-500 hover:text-violet-600 mb-6"
        >
          <ArrowLeft className="w-4 h-4" />
          返回
        </Link>

        <div className="flex items-center justify-between mb-6">
          <h1 className="text-2xl font-bold text-gray-900">历史记录</h1>
          <button
            onClick={handleRefresh}
            disabled={refreshing}
            title="重扫磁盘产物,同步对照/原文 PDF(用命令行重跑后点此刷新)"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium text-gray-600 border border-gray-200 hover:border-violet-300 hover:text-violet-600 transition-colors disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
            {refreshing ? '刷新中' : '刷新'}
          </button>
        </div>

        {error && <p className="text-sm text-red-500">{error}</p>}

        {tasks === null && !error && (
          <div className="flex items-center gap-2 text-gray-400 text-sm">
            <Loader2 className="w-4 h-4 animate-spin" />
            加载中...
          </div>
        )}

        {tasks !== null && tasks.length === 0 && (
          <div className="flex flex-col items-center justify-center py-20 text-center">
            <Inbox className="w-12 h-12 text-gray-300 mb-3" />
            <p className="text-gray-500 mb-1">还没有翻译记录</p>
            <Link href="/" className="text-violet-600 hover:text-violet-700 text-sm font-medium">
              去翻译第一篇论文 →
            </Link>
          </div>
        )}

        {tasks !== null && tasks.length > 0 && (
          <div className="grid gap-3">
            {tasks.map((t) => {
              const meta = STATUS_META[t.status] ?? STATUS_META.queued
              return (
                <Link
                  key={t.task_id}
                  href={`/task/${t.task_id}`}
                  className="flex items-center justify-between bg-white border border-gray-100 rounded-xl p-4 shadow-sm hover:border-violet-300 hover:shadow transition-all"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <div className="w-10 h-10 bg-violet-50 rounded-lg flex items-center justify-center text-violet-600 flex-shrink-0">
                      <FileText className="w-5 h-5" />
                    </div>
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-gray-900 truncate">
                        {t.title || t.source || t.task_id}
                      </p>
                      <p className="text-xs text-gray-400 truncate">
                        {fmtTime(t.created_at)}
                        {t.status === 'failed' && t.error ? ` · ${t.error}` : ''}
                      </p>
                    </div>
                  </div>
                  <span
                    className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium flex-shrink-0 ${meta.cls}`}
                  >
                    {meta.icon}
                    {meta.label}
                  </span>
                </Link>
              )
            })}
          </div>
        )}
      </div>
    </main>
  )
}
