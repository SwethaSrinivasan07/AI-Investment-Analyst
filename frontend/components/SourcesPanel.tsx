'use client'

import type { Source } from '@/lib/api'

interface SourcesPanelProps {
  sources: Source[]
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
      <div className="flex items-center gap-2 mb-3">
        <span className="text-[11px] font-medium uppercase tracking-widest text-[#5C5C5C]">
          Research Sources
        </span>
        <span className="text-[11px] bg-black/5 text-[#5C5C5C] border border-black/8 px-1.5 py-0.5 font-medium">
          {sources.length} {sources.length === 1 ? 'doc' : 'docs'}
        </span>
      </div>

      <div className="max-h-96 overflow-y-auto flex flex-col gap-2 pr-1">
        {sources.length === 0 ? (
          <p className="text-[#5C5C5C] text-[13px]">No source documents available.</p>
        ) : (
          sources.map((source, idx) => (
            <div
              key={source.chunk_id ?? idx}
              className="bg-white border border-black/8 p-3"
            >
              <div className="flex items-center gap-2 mb-1.5">
                <span className="text-[11px] font-medium px-1.5 py-0.5 bg-[#2E2A47]/6 text-[#2E2A47] border border-[#2E2A47]/15">
                  {source.doc_type}
                </span>
                {source.filing_date && (
                  <span className="text-[#5C5C5C] text-[11px]">
                    {formatFilingDate(source.filing_date)}
                  </span>
                )}
              </div>
              <p className="text-[#5C5C5C] text-[12px] leading-relaxed line-clamp-3">
                {truncate(source.text, 150)}
              </p>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
