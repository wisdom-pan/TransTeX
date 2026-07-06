'use client'

import { Sparkles, FileText, KeyRound, MessageSquare, Bot } from 'lucide-react'

const features = [
  { icon: Sparkles, label: '完全免费', color: 'text-green-600', bgColor: 'bg-green-50' },
  { icon: FileText, label: '文献翻译', color: 'text-violet-600', bgColor: 'bg-violet-50' },
  { icon: KeyRound, label: '关键术语', color: 'text-pink-600', bgColor: 'bg-pink-50' },
  { icon: Bot, label: 'AI摘要', color: 'text-rose-600', bgColor: 'bg-rose-50' },
  { icon: MessageSquare, label: 'AI对话', color: 'text-amber-600', bgColor: 'bg-amber-50' },
]

export default function Hero() {
  return (
    <div className="text-center py-12 md:py-16">
      {/* Main Title */}
      <h1 className="text-3xl md:text-4xl lg:text-5xl font-bold text-gray-900 mb-4">
        英文文献？现在是中文文献了
        <span className="inline-block ml-2 text-3xl md:text-4xl">😎</span>
      </h1>

      {/* Subtitle */}
      <p className="text-gray-500 text-base md:text-lg mb-8">
        用母语阅读论文，速度提升10倍
      </p>

      {/* Feature Tags */}
      <div className="flex flex-wrap justify-center gap-3 md:gap-4">
        {features.map((feature) => {
          const Icon = feature.icon
          return (
            <div
              key={feature.label}
              className={`flex items-center gap-2 px-4 py-2 rounded-full ${feature.bgColor} border border-transparent hover:border-gray-200 transition-all cursor-pointer`}
            >
              <Icon className={`w-4 h-4 ${feature.color}`} />
              <span className={`text-sm font-medium ${feature.color}`}>
                {feature.label}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
