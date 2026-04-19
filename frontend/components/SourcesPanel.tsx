'use client'

import type { Source } from '@/lib/api'

interface SourcesPanelProps {
  sources: Source[]
}

const docTypeBadge: Record<string, string> = {
  '10-K': 'bg-blue-900/60 text-blue-300 border border-blue-700/60',
  '10-Q': 'bg-purple-900/60 text-purple-300 border border-purple-700/60',
  '8-K':  'bg-orange-900/60 text-orange-300 border border-orange-700/60',
}

function getBadgeClass(docType: string): string {
  return docTypeBadge[docType] ?? 'bg-gray-700/60 text-gray-300 border border-gray-600/60'
}

function truncate(text: string, maxLen: number): string {
  if (text.length <= maxLen) return text
  return text.slice(0, maxLen).trimEnd() + '…'
}

function formatFilingDate(dateStr: string): string {
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

export default function SourcesPanel({ sources }: SourcesPanelProps) {
  return (
    <div>
      {/* Panel header */}
      <div className="flex items-center gap-2 mb-3">
        <span className="text-sm font-semibold text-gray-200">📄 Research Sources</span>
        <span className="text-xs bg-gray-700 text-gray-300 rounded-full px-2 py-0.5 font-medium">
          {sources.length} {sources.length === 1 ? 'document' : 'documents'}
        </span>
      </div>

      {/* Scrollable source list */}
      <div className="max-h-96 overflow-y-auto flex flex-col gap-2 pr-1">
        {sources.length === 0 ? (
          <p className="text-gray-500 text-sm">No source documents available.</p>
        ) : (
          sources.map((source, idx) => (
            <div
              key={source.chunk_id ?? idx}
              className="bg-gray-800 border border-gray-700 rounded-lg p-3"
            >
              <div className="flex items-center gap-2 mb-1">
                <span
                  className={`text-xs font-semibold px-1.5 py-0.5 rounded ${getBadgeClass(source.doc_type)}`}
                >
                  {source.doc_type}
                </span>
                {source.filing_date && (
                  <span className="text-gray-400 text-xs">
                    {formatFilingDate(source.filing_date)}
                  </span>
                )}
              </div>
              <p className="text-gray-300 text-sm mt-1 line-clamp-3">
                {truncate(source.text, 150)}
              </p>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
