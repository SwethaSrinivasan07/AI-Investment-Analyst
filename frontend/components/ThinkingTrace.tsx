'use client'

import { useState } from 'react'
import type { ThinkingBlock } from '@/lib/api'

interface ThinkingTraceProps {
  thinkingBlocks: ThinkingBlock[]
}

function wordCount(text: string): number {
  return text.trim().split(/\s+/).filter(Boolean).length
}

function estimateTokens(text: string): number {
  return Math.round(wordCount(text) / 1.33)
}

export default function ThinkingTrace({ thinkingBlocks }: ThinkingTraceProps) {
  const [expanded, setExpanded] = useState(false)

  if (!thinkingBlocks || thinkingBlocks.length === 0) return null

  const totalWords = thinkingBlocks.reduce((sum, b) => sum + wordCount(b.thinking), 0)
  const totalTokens = thinkingBlocks.reduce((sum, b) => sum + estimateTokens(b.thinking), 0)

  return (
    <div className="border border-black/8 bg-white overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 border-b border-black/8">
        <div className="flex items-center gap-3 flex-wrap">
          <div className="flex items-center gap-2">
            <svg
              className="w-3.5 h-3.5 text-[#5C5C5C] flex-shrink-0"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <path d="M9.5 2a2.5 2.5 0 0 1 0 5H9a7 7 0 0 0-7 7 3 3 0 0 0 3 3h1" />
              <path d="M14.5 2a2.5 2.5 0 0 0 0 5H15a7 7 0 0 1 7 7 3 3 0 0 1-3 3h-1" />
              <path d="M9 17a2 2 0 0 0 2 2h2a2 2 0 0 0 2-2v-1a2 2 0 0 1 2-2 2 2 0 0 0 2-2v-1a7 7 0 0 0-7-7 7 7 0 0 0-7 7v1a2 2 0 0 0 2 2 2 2 0 0 1 2 2v1z" />
            </svg>
            <span className="text-[13px] font-medium text-[#121212]">Analyst Reasoning</span>
          </div>

          <span className="text-[11px] font-medium px-1.5 py-0.5 bg-black/5 text-[#5C5C5C] border border-black/8 uppercase tracking-widest">
            Extended Thinking
          </span>

          <span className="text-[11px] text-[#5C5C5C]/70">
            ~{totalWords.toLocaleString()} words · ~{totalTokens.toLocaleString()} tokens
          </span>
        </div>

        <button
          onClick={() => setExpanded((prev) => !prev)}
          className="flex items-center gap-1.5 px-3 py-1 text-[12px] font-medium text-[#5C5C5C] hover:text-[#121212] bg-black/[0.03] hover:bg-black/[0.06] border border-black/8 transition-all duration-150 flex-shrink-0"
          aria-expanded={expanded}
        >
          {expanded ? 'Collapse' : 'Expand'}
          <svg
            className={`w-3 h-3 transition-transform duration-200 ${expanded ? 'rotate-180' : ''}`}
            fill="none" viewBox="0 0 24 24" stroke="currentColor"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </button>
      </div>

      <div className={`transition-all duration-200 overflow-hidden ${expanded ? 'max-h-[9999px] opacity-100' : 'max-h-0 opacity-0'}`}>
        <div className="p-4 flex flex-col gap-3">
          {thinkingBlocks.map((block, idx) => (
            <div key={idx} className="border border-black/8 border-l-2 border-l-[#2E2A47] overflow-hidden">
              <div className="flex items-center justify-between px-4 py-2 bg-[#F6F3EE] border-b border-black/8">
                <span className="text-[11px] font-medium uppercase tracking-widest text-[#5C5C5C]">
                  Internal Reasoning
                </span>
                <span className="text-[11px] text-[#5C5C5C]/60 font-medium">
                  Block {idx + 1} of {thinkingBlocks.length}
                </span>
              </div>

              <div className="px-4 py-3">
                <p className="text-[13px] leading-relaxed text-[#5C5C5C] whitespace-pre-wrap break-words font-mono">
                  {block.thinking}
                </p>
              </div>

              <div className="px-4 pb-3">
                <p className="text-[11px] italic text-[#5C5C5C]/50">
                  Claude&rsquo;s internal chain-of-thought before producing the final memo.
                </p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
