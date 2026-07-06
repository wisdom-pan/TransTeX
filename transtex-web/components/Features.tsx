'use client'

import { Languages, Sparkles, BookOpen, MessageCircle } from 'lucide-react'

const features = [
  {
    icon: Languages,
    title: '专业翻译',
    description: '获取准确的学术文献翻译',
    color: 'text-blue-600',
    bgColor: 'bg-blue-50',
    borderColor: 'border-blue-100',
  },
  {
    icon: Sparkles,
    title: 'AI智能摘要',
    description: '几秒钟内提取论文的核心观点',
    color: 'text-rose-600',
    bgColor: 'bg-rose-50',
    borderColor: 'border-rose-100',
  },
  {
    icon: BookOpen,
    title: '双语关键术语',
    description: '鼠标悬停即可查看专业术语的双语解释',
    color: 'text-violet-600',
    bgColor: 'bg-violet-50',
    borderColor: 'border-violet-100',
  },
  {
    icon: MessageCircle,
    title: '对话论文',
    description: '提问并获得关于论文内容的答案',
    color: 'text-amber-600',
    bgColor: 'bg-amber-50',
    borderColor: 'border-amber-100',
  },
]

export default function Features() {
  return (
    <div className="max-w-4xl mx-auto mt-16">
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
