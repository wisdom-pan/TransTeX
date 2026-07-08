'use client'

import { useEffect, useRef, useState, useCallback } from 'react'
import { Loader2 } from 'lucide-react'

// pdfjs-dist 只在客户端动态加载,避免 SSR 阶段引入。
// worker 从 public/ 提供(见 scripts:postinstall 或手动复制)。
type PdfjsModule = typeof import('pdfjs-dist')
let pdfjsPromise: Promise<PdfjsModule> | null = null

function loadPdfjs(): Promise<PdfjsModule> {
  if (!pdfjsPromise) {
    pdfjsPromise = import('pdfjs-dist').then((mod) => {
      mod.GlobalWorkerOptions.workerSrc = '/pdf.worker.min.mjs'
      return mod
    })
  }
  return pdfjsPromise
}

interface PdfViewerProps {
  src: string
  title: string
  scrollRef: React.RefObject<HTMLDivElement | null>
  onScroll: () => void
}

/** 把单个 PDF 逐页渲染成 canvas,放进可滚动容器。 */
function PdfViewer({ src, title, scrollRef, onScroll }: PdfViewerProps) {
  const pagesRef = useRef<HTMLDivElement | null>(null)
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')
  const [error, setError] = useState<string>('')

  useEffect(() => {
    let cancelled = false
    let renderTasks: Array<{ cancel: () => void }> = []

    async function render() {
      setStatus('loading')
      try {
        const pdfjs = await loadPdfjs()
        const doc = await pdfjs.getDocument(src).promise
        if (cancelled) return

        const container = pagesRef.current
        if (!container) return
        container.innerHTML = ''

        // 按容器宽度自适应缩放(留出内边距)
        const targetWidth = (scrollRef.current?.clientWidth ?? 600) - 24

        for (let i = 1; i <= doc.numPages; i++) {
          if (cancelled) return
          const page = await doc.getPage(i)
          const baseViewport = page.getViewport({ scale: 1 })
          const scale = targetWidth / baseViewport.width
          const viewport = page.getViewport({ scale })

          const canvas = document.createElement('canvas')
          const ctx = canvas.getContext('2d')
          if (!ctx) continue
          const dpr = window.devicePixelRatio || 1
          canvas.width = viewport.width * dpr
          canvas.height = viewport.height * dpr
          canvas.style.width = `${viewport.width}px`
          canvas.style.height = `${viewport.height}px`
          canvas.style.display = 'block'
          canvas.style.margin = '0 auto 8px'
          canvas.style.boxShadow = '0 1px 3px rgba(0,0,0,0.1)'
          container.appendChild(canvas)

          const task = page.render({
            canvasContext: ctx,
            viewport,
            transform: dpr !== 1 ? [dpr, 0, 0, dpr, 0, 0] : undefined,
          })
          renderTasks.push(task)
          await task.promise.catch(() => {})
        }
        if (!cancelled) setStatus('ready')
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : '加载失败')
          setStatus('error')
        }
      }
    }

    render()
    return () => {
      cancelled = true
      renderTasks.forEach((t) => t.cancel())
    }
  }, [src, scrollRef])

  return (
    <div className="flex flex-col rounded-xl border border-gray-200 bg-white overflow-hidden shadow-sm">
      <div className="px-4 py-2 border-b border-gray-100 bg-gray-50 text-sm font-medium text-gray-700 flex items-center justify-between">
        <span>{title}</span>
        {status === 'loading' && <Loader2 className="w-4 h-4 animate-spin text-gray-400" />}
      </div>
      <div
        ref={scrollRef}
        onScroll={onScroll}
        className="relative h-[75vh] overflow-y-auto bg-gray-100 px-3 py-3"
      >
        {status === 'error' && (
          <p className="text-sm text-red-500 p-4">PDF 加载失败:{error}</p>
        )}
        <div ref={pagesRef} />
      </div>
    </div>
  )
}

interface PdfCompareProps {
  leftSrc: string
  rightSrc: string
  leftTitle?: string
  rightTitle?: string
}

/** 并排两个 PDF,按滚动比例双向同步。 */
export default function PdfCompare({
  leftSrc,
  rightSrc,
  leftTitle = '英文原文',
  rightTitle = '中文译文',
}: PdfCompareProps) {
  const leftRef = useRef<HTMLDivElement | null>(null)
  const rightRef = useRef<HTMLDivElement | null>(null)
  const [synced, setSynced] = useState(true)
  // 防回环:一侧被程序滚动时,忽略它触发的 onScroll
  const lockRef = useRef<'left' | 'right' | null>(null)

  const syncFrom = useCallback(
    (from: 'left' | 'right') => {
      if (!synced) return
      // 若这次滚动是程序设置的(锁定的另一侧回调),直接跳过
      if (lockRef.current && lockRef.current !== from) return

      const src = from === 'left' ? leftRef.current : rightRef.current
      const dst = from === 'left' ? rightRef.current : leftRef.current
      if (!src || !dst) return

      const srcMax = src.scrollHeight - src.clientHeight
      const dstMax = dst.scrollHeight - dst.clientHeight
      if (srcMax <= 0 || dstMax <= 0) return

      const ratio = src.scrollTop / srcMax
      lockRef.current = from
      dst.scrollTop = ratio * dstMax
      // 下一帧解锁,让目标侧的 onScroll 被忽略掉
      requestAnimationFrame(() => {
        lockRef.current = null
      })
    },
    [synced],
  )

  return (
    <div>
      <div className="flex items-center justify-end mb-2">
        <label className="flex items-center gap-2 text-sm text-gray-500 cursor-pointer select-none">
          <input
            type="checkbox"
            checked={synced}
            onChange={(e) => setSynced(e.target.checked)}
            className="rounded border-gray-300 text-violet-600 focus:ring-violet-500"
          />
          同步滚动
        </label>
      </div>
      <div className="grid md:grid-cols-2 gap-4">
        <PdfViewer
          src={leftSrc}
          title={leftTitle}
          scrollRef={leftRef}
          onScroll={() => syncFrom('left')}
        />
        <PdfViewer
          src={rightSrc}
          title={rightTitle}
          scrollRef={rightRef}
          onScroll={() => syncFrom('right')}
        />
      </div>
    </div>
  )
}
