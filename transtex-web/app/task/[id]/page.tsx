'use client'

import { use, useState } from 'react'
import dynamic from 'next/dynamic'
import Link from 'next/link'
import { ArrowLeft, Download, FileText, Columns, Eye, EyeOff, ExternalLink } from 'lucide-react'
import Navbar from '@/components/Navbar'
import ProgressTracker from '@/components/ProgressTracker'
import { useTaskSocket } from '@/lib/useTaskSocket'
import { downloadUrl, previewUrl } from '@/lib/api'

// PDF 渲染依赖浏览器 API,禁用 SSR
const PdfCompare = dynamic(() => import('@/components/PdfCompare'), {
  ssr: false,
  loading: () => <p className="text-sm text-gray-400 py-8 text-center">正在加载预览…</p>,
})

export default function TaskPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params)
  const { progress, finalStatus } = useTaskSocket(id)
  const [showPreview, setShowPreview] = useState(true)

  const done = progress.status === 'done'
  const failed = progress.status === 'failed'
  const artifacts = finalStatus?.artifacts
  // 中英并排预览需要原文与译文两份 PDF 都就绪
  const canCompare = Boolean(artifacts?.original_pdf && artifacts?.translated_pdf)

  return (
    <main className="min-h-screen bg-gradient-to-b from-slate-50 to-white">
      <Navbar />
      <div className="container mx-auto px-4 pt-8 pb-16 max-w-5xl">
        <Link
          href="/"
          className="inline-flex items-center gap-1 text-sm text-gray-500 hover:text-violet-600 mb-6"
        >
          <ArrowLeft className="w-4 h-4" />
          返回
        </Link>

        <h1 className="text-2xl font-bold text-gray-900 mb-1">
          {done ? '翻译完成 🎉' : failed ? '翻译失败' : '正在翻译...'}
        </h1>
        <p className="text-sm text-gray-500 mb-6 font-mono">任务 {id}</p>

        <div className="max-w-2xl">
          <ProgressTracker progress={progress} />
        </div>

        {/* 中英对照预览 */}
        {done && canCompare && (
          <section className="mt-8">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-lg font-semibold text-gray-900 flex items-center gap-2">
                <Columns className="w-5 h-5 text-violet-600" />
                中英对照预览
              </h2>
              <div className="flex items-center gap-3">
                <a
                  href={`/task/${id}/preview`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-sm text-gray-500 hover:text-violet-600"
                >
                  <ExternalLink className="w-4 h-4" />
                  新窗口打开
                </a>
                <button
                  onClick={() => setShowPreview((v) => !v)}
                  className="inline-flex items-center gap-1 text-sm text-gray-500 hover:text-violet-600"
                >
                  {showPreview ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  {showPreview ? '收起' : '展开'}
                </button>
              </div>
            </div>

            {showPreview && (
              <PdfCompare
                leftSrc={previewUrl(id, 'original')}
                rightSrc={previewUrl(id, 'translated')}
              />
            )}
          </section>
        )}

        {/* 下载区 */}
        {done && artifacts && (
          <section className="mt-8">
            <h2 className="text-lg font-semibold text-gray-900 mb-3">下载</h2>
            <div className="grid sm:grid-cols-2 gap-3">
              {artifacts.translated_pdf && (
                <DownloadCard
                  href={downloadUrl(id, 'translated')}
                  icon={<FileText className="w-5 h-5" />}
                  title="中文译文 PDF"
                  desc="全文翻译版"
                />
              )}
              {artifacts.bilingual_pdf && (
                <DownloadCard
                  href={downloadUrl(id, 'bilingual')}
                  icon={<Columns className="w-5 h-5" />}
                  title="中英对照 PDF"
                  desc="左右双栏对照版"
                />
              )}
              {artifacts.original_pdf && (
                <DownloadCard
                  href={downloadUrl(id, 'original')}
                  icon={<FileText className="w-5 h-5" />}
                  title="英文原文 PDF"
                  desc="重新编译的原版"
                />
              )}
            </div>
          </section>
        )}
      </div>
    </main>
  )
}

function DownloadCard({
  href,
  icon,
  title,
  desc,
}: {
  href: string
  icon: React.ReactNode
  title: string
  desc: string
}) {
  return (
    <a
      href={href}
      className="flex items-center justify-between bg-white border border-gray-100 rounded-xl p-4 shadow-sm hover:border-violet-300 hover:shadow transition-all"
    >
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 bg-violet-50 rounded-lg flex items-center justify-center text-violet-600">
          {icon}
        </div>
        <div>
          <p className="text-sm font-medium text-gray-900">{title}</p>
          <p className="text-xs text-gray-500">{desc}</p>
        </div>
      </div>
      <Download className="w-5 h-5 text-gray-400" />
    </a>
  )
}
