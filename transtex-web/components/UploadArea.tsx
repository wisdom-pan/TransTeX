'use client'

import { useCallback, useState } from 'react'
import { useRouter } from 'next/navigation'
import { Link2, Upload, File, X, Loader2 } from 'lucide-react'
import { createTask, uploadTask } from '@/lib/api'

type Mode = 'arxiv' | 'upload'

export default function UploadArea() {
  const router = useRouter()
  const [mode, setMode] = useState<Mode>('arxiv')
  const [arxivInput, setArxivInput] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [isDragOver, setIsDragOver] = useState(false)
  const [bilingual, setBilingual] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragOver(false)
    const f = Array.from(e.dataTransfer.files).find(
      (x) => x.name.endsWith('.zip') || x.name.endsWith('.tar.gz') || x.name.endsWith('.tgz'),
    )
    if (f) setFile(f)
  }, [])

  const submit = useCallback(async () => {
    setError(null)
    setSubmitting(true)
    try {
      let taskId: string
      if (mode === 'arxiv') {
        if (!arxivInput.trim()) throw new Error('请输入 arXiv 链接或 ID')
        const r = await createTask({ arxiv_url: arxivInput.trim(), make_bilingual: bilingual })
        taskId = r.task_id
      } else {
        if (!file) throw new Error('请选择源码压缩包')
        const r = await uploadTask(file, { make_bilingual: bilingual })
        taskId = r.task_id
      }
      router.push(`/task/${taskId}`)
    } catch (e) {
      setError(e instanceof Error ? e.message : '提交失败')
      setSubmitting(false)
    }
  }, [mode, arxivInput, file, bilingual, router])

  return (
    <div className="max-w-2xl mx-auto">
      {/* Tab 切换 */}
      <div className="flex gap-2 mb-4 justify-center">
        <TabButton active={mode === 'arxiv'} onClick={() => setMode('arxiv')} icon={<Link2 className="w-4 h-4" />}>
          arXiv 链接
        </TabButton>
        <TabButton active={mode === 'upload'} onClick={() => setMode('upload')} icon={<Upload className="w-4 h-4" />}>
          上传源码
        </TabButton>
      </div>

      <div className="bg-white rounded-2xl shadow-lg border border-gray-100 p-6 md:p-8">
        {mode === 'arxiv' ? (
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              arXiv 链接或论文 ID
            </label>
            <input
              type="text"
              value={arxivInput}
              onChange={(e) => setArxivInput(e.target.value)}
              placeholder="https://arxiv.org/abs/2606.20781 或 2606.20781"
              className="w-full px-4 py-3 border border-gray-200 rounded-lg focus:outline-none focus:border-violet-500 focus:ring-1 focus:ring-violet-500"
              onKeyDown={(e) => e.key === 'Enter' && submit()}
            />
            <p className="text-xs text-gray-400 mt-2">
              粘贴 arXiv 论文链接,自动下载 LaTeX 源码并翻译为中文
            </p>
          </div>
        ) : (
          <div
            className={`border-2 border-dashed rounded-xl p-8 text-center transition-all ${
              isDragOver ? 'border-violet-500 bg-violet-50/50' : 'border-gray-200 hover:border-violet-300'
            }`}
            onDragOver={(e) => {
              e.preventDefault()
              setIsDragOver(true)
            }}
            onDragLeave={(e) => {
              e.preventDefault()
              setIsDragOver(false)
            }}
            onDrop={handleDrop}
          >
            {file ? (
              <div className="flex items-center justify-between bg-gray-50 p-3 rounded-lg">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 bg-violet-50 rounded-lg flex items-center justify-center">
                    <File className="w-5 h-5 text-violet-500" />
                  </div>
                  <div className="text-left">
                    <p className="text-sm font-medium text-gray-900 truncate max-w-[240px]">{file.name}</p>
                    <p className="text-xs text-gray-500">{(file.size / 1024 / 1024).toFixed(2)} MB</p>
                  </div>
                </div>
                <button onClick={() => setFile(null)} className="p-1.5 text-gray-400 hover:text-red-500 rounded-lg">
                  <X className="w-4 h-4" />
                </button>
              </div>
            ) : (
              <>
                <div className="w-14 h-14 bg-violet-600 rounded-full flex items-center justify-center mx-auto mb-4">
                  <Upload className="w-7 h-7 text-white" />
                </div>
                <p className="text-gray-700 mb-2">拖拽 LaTeX 源码压缩包到这里</p>
                <label className="text-violet-600 hover:text-violet-700 cursor-pointer font-medium text-sm">
                  点击选择文件
                  <input
                    type="file"
                    accept=".zip,.tar.gz,.tgz"
                    className="hidden"
                    onChange={(e) => e.target.files && setFile(e.target.files[0])}
                  />
                </label>
                <p className="text-xs text-gray-400 mt-2">支持 .zip / .tar.gz(arXiv e-print 源码)</p>
              </>
            )}
          </div>
        )}

        {/* 选项 */}
        <label className="flex items-center gap-2 mt-4 text-sm text-gray-600 cursor-pointer">
          <input
            type="checkbox"
            checked={bilingual}
            onChange={(e) => setBilingual(e.target.checked)}
            className="rounded border-gray-300 text-violet-600 focus:ring-violet-500"
          />
          生成中英对照 PDF
        </label>

        {error && <p className="text-sm text-red-500 mt-3">{error}</p>}

        <button
          onClick={submit}
          disabled={submitting}
          className="w-full mt-5 bg-violet-600 hover:bg-violet-700 disabled:opacity-60 text-white py-3 rounded-lg font-medium transition-colors flex items-center justify-center gap-2"
        >
          {submitting && <Loader2 className="w-4 h-4 animate-spin" />}
          {submitting ? '提交中...' : '开始翻译'}
        </button>
      </div>
    </div>
  )
}

function TabButton({
  active,
  onClick,
  icon,
  children,
}: {
  active: boolean
  onClick: () => void
  icon: React.ReactNode
  children: React.ReactNode
}) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-2 px-5 py-2 rounded-full text-sm font-medium transition-all ${
        active ? 'bg-violet-600 text-white shadow-sm' : 'bg-white text-gray-600 border border-gray-200 hover:border-violet-300'
      }`}
    >
      {icon}
      {children}
    </button>
  )
}
