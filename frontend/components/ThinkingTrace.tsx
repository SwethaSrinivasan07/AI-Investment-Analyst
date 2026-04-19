'use client'

import { useState } from 'react'
import type { ThinkingBlock } from '@/lib/api'

interface ThinkingTraceProps {
  thinkingBlocks: ThinkingBlock[]
}

export default function ThinkingTrace({ thinkingBlocks }: ThinkingTraceProps) {
  const [expanded, setExpanded] = useState(false)

  if (!thinkingBlocks || thinkingBlocks.length === 0) {
    return null
  }

  return (
    <div>
      <button
        onClick={() => setExpanded((prev) => !prev)}
        className="text-indigo-400 hover:text-indigo-300 text-sm flex items-center gap-2 transition"
        aria-expanded={expanded}
      >
        <svg
          className={`w-4 h-4 transition-transform ${expanded ? 'rotate-90' : ''}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          aria-hidden="true"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
        </svg>
        {expanded ? 'Hide Analyst Reasoning' : '🧠 Show Analyst Reasoning'}
      </button>

      {expanded && (
        <div className="mt-3 flex flex-col gap-3">
          {thinkingBlocks.map((block, idx) => (
            <div
              key={idx}
              className="bg-gray-800/50 border border-gray-700 rounded-lg p-4"
            >
              <span className="inline-block mb-2 text-xs font-semibold uppercase tracking-wider text-gray-500 bg-gray-700/60 rounded px-2 py-0.5">
                Extended Thinking
              </span>
              <pre className="text-sm font-mono text-gray-300 whitespace-pre-wrap break-words leading-relaxed">
                {block.thinking}
              </pre>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
