'use client'

import { useRouter } from 'next/navigation'
import type { Memo } from '@/lib/api'

interface MemoCardProps {
  memo: Memo
}

const recommendationColors: Record<string, string> = {
  Buy:   'bg-[#2F6B4F]/8 text-[#2F6B4F] border border-[#2F6B4F]/20',
  Watch: 'bg-[#6B7280]/8 text-[#6B7280] border border-[#6B7280]/20',
  Pass:  'bg-[#A14A44]/8 text-[#A14A44] border border-[#A14A44]/20',
}

const convictionColors: Record<string, string> = {
  High:   'text-[#2F6B4F]',
  Medium: 'text-[#6B7280]',
  Low:    'text-[#A14A44]',
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
  const recClass = recommendationColors[memo.recommendation] ?? 'bg-black/5 text-[#5C5C5C] border border-black/8'
  const convClass = convictionColors[memo.conviction] ?? 'text-[#5C5C5C]'

  return (
    <div
      onClick={() => router.push(`/memo/${memo.id}`)}
      className="bg-white border border-black/8 p-4 hover:border-black/20 cursor-pointer transition-colors group"
    >
      {/* Top row: ticker + recommendation */}
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="min-w-0">
          <span className="font-serif text-[18px] text-[#121212] group-hover:text-[#2E2A47] transition-colors leading-tight block">
            {memo.ticker}
          </span>
          <p className="text-[12px] text-[#5C5C5C] truncate mt-0.5">{memo.company_name}</p>
        </div>
        <span className={`shrink-0 text-[11px] font-medium px-1.5 py-0.5 ${recClass}`}>
          {memo.recommendation}
        </span>
      </div>

      {/* Metadata row */}
      <div className="flex flex-wrap gap-1.5 mb-3">
        <span className="text-[11px] px-1.5 py-0.5 text-[#5C5C5C] border border-black/8 uppercase tracking-wide">
          {memo.strategy}
        </span>
        <span className="text-[11px] px-1.5 py-0.5 text-[#5C5C5C] border border-black/8">
          {memo.sector}
        </span>
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between text-[11px] border-t border-black/8 pt-2.5 mt-2.5">
        <span className="text-[#5C5C5C]">
          Conviction:{' '}
          <span className={`font-medium ${convClass}`}>{memo.conviction}</span>
        </span>
        <span className="text-[#5C5C5C]">{formatDate(memo.created_at)}</span>
      </div>
    </div>
  )
}
