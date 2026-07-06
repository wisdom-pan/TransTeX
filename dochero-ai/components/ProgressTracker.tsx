'use client'

import { Check, Loader2, Circle } from 'lucide-react'
import { ProgressState } from '@/lib/useTaskSocket'

// 流水线阶段顺序与中文标签
const STAGES: { key: string; label: string }[] = [
  { key: 'downloading', label: '下载源码' },
  { key: 'splitting', label: '解析分段' },
  { key: 'translating', label: '翻译' },
  { key: 'merging', label: '合并' },
  { key: 'compiling', label: '编译 PDF' },
  { key: 'bilingual', label: '中英对照' },
  { key: 'done', label: '完成' },
]

function stageIndex(stage: string): number {
  const i = STAGES.findIndex((s) => s.key === stage)
  return i === -1 ? 0 : i
}

export default function ProgressTracker({ progress }: { progress: ProgressState }) {
  const failed = progress.status === 'failed'
  const done = progress.status === 'done'
  const activeIdx = done ? STAGES.length - 1 : stageIndex(progress.stage)
  const pct =
    progress.total > 0 ? Math.round((progress.current / progress.total) * 100) : 0

  return (
    <div className="bg-white rounded-2xl shadow-lg border border-gray-100 p-6 md:p-8">
      {/* 阶段列表 */}
      <ol className="space-y-3">
        {STAGES.map((s, idx) => {
          const state =
            failed && idx === activeIdx
              ? 'failed'
              : idx < activeIdx || done
              ? 'done'
              : idx === activeIdx
              ? 'active'
              : 'pending'
          return (
            <li key={s.key} className="flex items-center gap-3">
              <span className="flex-shrink-0">
                {state === 'done' ? (
                  <span className="w-6 h-6 rounded-full bg-green-500 flex items-center justify-center">
                    <Check className="w-4 h-4 text-white" />
                  </span>
                ) : state === 'active' ? (
                  <span className="w-6 h-6 rounded-full bg-violet-100 flex items-center justify-center">
                    <Loader2 className="w-4 h-4 text-violet-600 animate-spin" />
                  </span>
                ) : state === 'failed' ? (
                  <span className="w-6 h-6 rounded-full bg-red-500 flex items-center justify-center text-white text-xs">
                    !
                  </span>
                ) : (
                  <Circle className="w-6 h-6 text-gray-300" />
                )}
              </span>
              <span
                className={`text-sm font-medium ${
                  state === 'pending' ? 'text-gray-400' : 'text-gray-800'
                }`}
              >
                {s.label}
              </span>
              {/* 翻译阶段显示细粒度进度 */}
              {state === 'active' && s.key === 'translating' && progress.total > 0 && (
                <span className="text-xs text-gray-500 ml-auto">
                  {progress.current}/{progress.total}
                </span>
              )}
            </li>
          )
        })}
      </ol>

      {/* 翻译进度条 */}
      {progress.stage === 'translating' && progress.total > 0 && !done && (
        <div className="mt-5">
          <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
            <div
              className="h-full bg-violet-500 transition-all duration-300"
              style={{ width: `${pct}%` }}
            />
          </div>
        </div>
      )}

      {/* 当前消息 */}
      {progress.message && !done && (
        <p className="mt-4 text-xs text-gray-500 truncate">{progress.message}</p>
      )}
      {failed && progress.error && (
        <p className="mt-4 text-sm text-red-500">错误:{progress.error}</p>
      )}
    </div>
  )
}
