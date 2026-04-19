'use client'

import { useRouter } from 'next/navigation'
import type { Memo } from '@/lib/api'

interface MemoCardProps {
  memo: Memo
}

const strategyColors: Record<string, string> = {
  momentum: 'bg-blue-900/50 text-blue-300 border border-blue-700/50',
  value: 'bg-green-900/50 text-green-300 border border-green-700/50',
  growth: 'bg-purple-900/50 text-purple-300 border border-purple-700/50',
  dividend: 'bg-yellow-900/50 text-yellow-300 border border-yellow-700/50',
}

const recommendationColors: Record<string, string> = {
  Buy: 'bg-green-900/60 text-green-300 border border-green-700/50',
  Watch: 'bg-yellow-900/60 text-yellow-300 border border-yellow-700/50',
  Pass: 'bg-red-900/60 text-red-300 border border-red-700/50',
}

const convictionColors: Record<string, string> = {
  High: 'text-green-400',
  Medium: 'text-yellow-400',
  Low: 'text-red-400',
}

function formatDate(dateStr: string): string {
  try {
    return new Date(dateStr).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    })
  } catch {
    return dateStr
  }
}

export default function MemoCard({ memo }: MemoCardProps) {
  const router = useRouter()
  const strategyKey = memo.strategy?.toLowerCase() ?? ''
  const strategyClass = strategyColors[strategyKey] ?? 'bg-gray-800 text-gray-300 border border-gray-700'
  const recClass = recommendationColors[memo.recommendation] ?? 'bg-gray-800 text-gray-300 border border-gray-700'
  const convClass = convictionColors[memo.conviction] ?? 'text-gray-400'

  return (
    <div
      onClick={() => router.push(`/memo/${memo.id}`)}
      className="bg-gray-900 border border-gray-800 rounded-xl p-5 hover:border-gray-600 cursor-pointer transition-all duration-150 hover:shadow-lg hover:shadow-black/30 group"
    >
      {/* Top row: ticker + recommendation */}
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="min-w-0">
          <span className="text-xl font-bold text-white group-hover:text-indigo-300 transition-colors">
            {memo.ticker}
          </span>
          <p className="text-sm text-gray-400 truncate mt-0.5">{memo.company_name}</p>
        </div>
        <span className={`shrink-0 text-xs font-semibold px-2.5 py-1 rounded-md ${recClass}`}>
          {memo.recommendation}
        </span>
      </div>

      {/* Badges row */}
      <div className="flex flex-wrap gap-2 mb-4">
        <span className={`text-xs font-medium px-2.5 py-1 rounded-md capitalize ${strategyClass}`}>
          {memo.strategy}
        </span>
        <span className="text-xs font-medium px-2.5 py-1 rounded-md bg-gray-800 text-gray-300 border border-gray-700">
          {memo.sector}
        </span>
      </div>

      {/* Conviction + date */}
      <div className="flex items-center justify-between text-xs">
        <span className="text-gray-500">
          Conviction:{' '}
          <span className={`font-semibold ${convClass}`}>{memo.conviction}</span>
        </span>
        <span className="text-gray-600">{formatDate(memo.created_at)}</span>
      </div>
    </div>
  )
}
