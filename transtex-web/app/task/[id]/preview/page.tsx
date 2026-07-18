'use client'

import { use } from 'react'
import dynamic from 'next/dynamic'
import Link from 'next/link'
import { ArrowLeft } from 'lucide-react'
import { previewUrl } from '@/lib/api'

// PDF 渲染依赖浏览器 API,禁用 SSR
const PdfCompare = dynamic(() => import('@/components/PdfCompare'), {
  ssr: false,
  loading: () => <p className="text-sm text-gray-400 py-8 text-center">正在加载预览…</p>,
})

// 独立全屏预览页:用整块视窗承载中英对照,显示区域远大于任务页内嵌版本。
export default function PreviewPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params)

  return (
    <main className="h-screen flex flex-col bg-gradient-to-b from-slate-50 to-white">
      <header className="flex items-center justify-between px-4 py-2 border-b border-gray-100 bg-white/80 backdrop-blur">
        <Link
          href={`/task/${id}`}
          className="inline-flex items-center gap-1 text-sm text-gray-500 hover:text-violet-600"
        >
          <ArrowLeft className="w-4 h-4" />
          返回任务
        </Link>
        <span className="text-sm text-gray-400 font-mono">中英对照预览 · {id}</span>
      </header>
      <div className="flex-1 min-h-0 px-4 py-3">
        <PdfCompare
          leftSrc={previewUrl(id, 'original')}
          rightSrc={previewUrl(id, 'translated')}
          heightClass="h-[calc(100vh-4.5rem)]"
        />
      </div>
    </main>
  )
}
