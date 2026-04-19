'use client'

import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { Memo } from '@/lib/api'

interface MemoDetailProps {
  memo: Memo
}

const recommendationColors: Record<string, string> = {
  Buy: 'bg-green-900/60 text-green-300 border border-green-700/60',
  Watch: 'bg-yellow-900/60 text-yellow-300 border border-yellow-700/60',
  Pass: 'bg-red-900/60 text-red-300 border border-red-700/60',
}

const convictionColors: Record<string, string> = {
  High: 'text-green-400',
  Medium: 'text-yellow-400',
  Low: 'text-red-400',
}

function formatDate(dateStr: string): string {
  try {
    return new Date(dateStr).toLocaleDateString('en-US', {
      weekday: 'short',
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    })
  } catch {
    return dateStr
  }
}

export default function MemoDetail({ memo }: MemoDetailProps) {
  const recClass =
    recommendationColors[memo.recommendation] ??
    'bg-gray-800 text-gray-300 border border-gray-700'
  const convClass = convictionColors[memo.conviction] ?? 'text-gray-400'

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="mb-6 pb-6 border-b border-gray-800">
        <div className="flex flex-wrap items-start justify-between gap-4 mb-3">
          <div>
            <h1 className="text-3xl font-bold text-white">{memo.ticker}</h1>
            <p className="text-lg text-gray-400 mt-1">{memo.company_name}</p>
          </div>
          <span className={`text-sm font-bold px-3 py-1.5 rounded-lg ${recClass}`}>
            {memo.recommendation}
          </span>
        </div>

        <div className="flex flex-wrap items-center gap-4 text-sm">
          <div>
            <span className="text-gray-500">Conviction: </span>
            <span className={`font-semibold ${convClass}`}>{memo.conviction}</span>
          </div>
          <div>
            <span className="text-gray-500">Strategy: </span>
            <span className="text-gray-300 capitalize">{memo.strategy}</span>
          </div>
          <div>
            <span className="text-gray-500">Sector: </span>
            <span className="text-gray-300">{memo.sector}</span>
          </div>
          {memo.data_as_of && (
            <div>
              <span className="text-gray-500">Data as of: </span>
              <span className="text-gray-300">{formatDate(memo.data_as_of)}</span>
            </div>
          )}
        </div>

        {/* Eval scores */}
        {memo.eval_scores && Object.keys(memo.eval_scores).length > 0 && (
          <div className="mt-4 flex flex-wrap gap-3">
            {Object.entries(memo.eval_scores).map(([key, value]) => (
              <div
                key={key}
                className="flex items-center gap-1.5 bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5"
              >
                <span className="text-xs text-gray-400 capitalize">{key.replace(/_/g, ' ')}</span>
                <span className="text-xs font-bold text-indigo-400">
                  {typeof value === 'number' ? value.toFixed(1) : value}
                </span>
              </div>
            ))}
          </div>
        )}

        {/* Disclaimer */}
        <p className="mt-4 text-xs text-gray-600 italic">
          For educational use only. Not financial advice.
        </p>
      </div>

      {/* Memo body */}
      <div className="flex-1 overflow-y-auto">
        <div className="prose prose-invert max-w-none prose-sm
          prose-headings:text-gray-100
          prose-h1:text-2xl prose-h1:font-bold prose-h1:mt-6 prose-h1:mb-3
          prose-h2:text-xl prose-h2:font-semibold prose-h2:mt-5 prose-h2:mb-2
          prose-h3:text-lg prose-h3:font-medium prose-h3:mt-4 prose-h3:mb-2
          prose-p:text-gray-300 prose-p:leading-relaxed
          prose-strong:text-gray-100
          prose-a:text-indigo-400 prose-a:no-underline hover:prose-a:underline
          prose-code:text-indigo-300 prose-code:bg-gray-800 prose-code:px-1 prose-code:py-0.5 prose-code:rounded prose-code:text-xs
          prose-pre:bg-gray-800 prose-pre:border prose-pre:border-gray-700
          prose-table:text-sm
          prose-th:text-gray-200 prose-th:bg-gray-800 prose-th:px-3 prose-th:py-2
          prose-td:text-gray-300 prose-td:px-3 prose-td:py-2 prose-td:border-b prose-td:border-gray-800
          prose-blockquote:border-l-4 prose-blockquote:border-indigo-600 prose-blockquote:text-gray-400
          prose-li:text-gray-300
          prose-hr:border-gray-800
        ">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>
            {memo.markdown_text}
          </ReactMarkdown>
        </div>
      </div>
    </div>
  )
}
