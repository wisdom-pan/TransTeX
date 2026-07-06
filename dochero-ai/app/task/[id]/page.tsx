'use client'

import { use } from 'react'
import Link from 'next/link'
import { ArrowLeft, Download, FileText, Columns } from 'lucide-react'
import Navbar from '@/components/Navbar'
import ProgressTracker from '@/components/ProgressTracker'
import { useTaskSocket } from '@/lib/useTaskSocket'
import { downloadUrl } from '@/lib/api'

export default function TaskPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params)
  const { progress, finalStatus } = useTaskSocket(id)

  const done = progress.status === 'done'
  const failed = progress.status === 'failed'

  return (
    <main className="min-h-screen bg-gradient-to-b from-slate-50 to-white">
      <Navbar />
      <div className="container mx-auto px-4 pt-8 pb-16 max-w-2xl">
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

        <ProgressTracker progress={progress} />

        {/* 下载区 */}
        {done && finalStatus && (
          <div className="mt-6 grid gap-3">
            {finalStatus.artifacts.translated_pdf && (
              <DownloadCard
                href={downloadUrl(id, 'translated')}
                icon={<FileText className="w-5 h-5" />}
                title="中文译文 PDF"
                desc="全文翻译版"
              />
            )}
            {finalStatus.artifacts.bilingual_pdf && (
              <DownloadCard
                href={downloadUrl(id, 'bilingual')}
                icon={<Columns className="w-5 h-5" />}
                title="中英对照 PDF"
                desc="左右双栏对照版"
              />
            )}
          </div>
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
