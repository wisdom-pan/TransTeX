'use client'

import { Layers, FileCode, Columns, BookMarked } from 'lucide-react'

const features = [
  {
    icon: Layers,
    title: '排版无损',
    description: '公式、图表、引用、参考文献原样保留，译文与原版布局一致',
    color: 'text-blue-600',
    bgColor: 'bg-blue-50',
    borderColor: 'border-blue-100',
  },
  {
    icon: FileCode,
    title: 'LaTeX 原生编译',
    description: '直接翻译 .tex 源码并用 xelatex 编译，输出真正的 PDF 而非图片',
    color: 'text-rose-600',
    bgColor: 'bg-rose-50',
    borderColor: 'border-rose-100',
  },
  {
    icon: Columns,
    title: '中英对照',
    description: '左原文右译文双栏对照 PDF，页面内可并排预览，方便逐段校对',
    color: 'text-violet-600',
    bgColor: 'bg-violet-50',
    borderColor: 'border-violet-100',
  },
  {
    icon: BookMarked,
    title: '术语统一',
    description: '先扫描全文高频术语生成统一术语表，保证全篇译名前后一致',
    color: 'text-amber-600',
    bgColor: 'bg-amber-50',
    borderColor: 'border-amber-100',
  },
]

export default function Features() {
  return (
    <div id="features" className="max-w-4xl mx-auto mt-16 scroll-mt-20">
      <h3 className="text-center text-lg font-semibold text-gray-900 mb-6">功能一览</h3>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {features.map((feature) => {
          const Icon = feature.icon
          return (
            <div
              key={feature.title}
              className={`flex items-start gap-4 p-5 rounded-xl ${feature.bgColor} border ${feature.borderColor} hover:shadow-md transition-shadow`}
            >
              <div className={`w-10 h-10 rounded-lg bg-white flex items-center justify-center flex-shrink-0 shadow-sm`}>
                <Icon className={`w-5 h-5 ${feature.color}`} />
              </div>
              <div>
                <h4 className={`font-semibold ${feature.color} mb-1`}>
                  {feature.title}
                </h4>
                <p className="text-sm text-gray-600 leading-relaxed">
                  {feature.description}
                </p>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
