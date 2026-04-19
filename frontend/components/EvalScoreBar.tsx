'use client'

import type { EvalScores } from '@/lib/api'

interface EvalScoreBarProps {
  scores: EvalScores
}

type DimensionKey = Exclude<keyof EvalScores, 'overall' | 'rationale'>

const DIMENSIONS: { key: DimensionKey; label: string }[] = [
  { key: 'data_grounding',   label: 'Data Grounding' },
  { key: 'thesis_clarity',   label: 'Thesis Clarity' },
  { key: 'risk_depth',       label: 'Risk Depth' },
  { key: 'valuation_rigor',  label: 'Valuation Rigor' },
  { key: 'actionability',    label: 'Actionability' },
]

function overallColor(score: number): string {
  if (score >= 4) return 'text-green-400'
  if (score >= 3) return 'text-yellow-400'
  return 'text-red-400'
}

function barColor(score: number): string {
  if (score >= 4) return 'bg-green-500'
  if (score >= 3) return 'bg-yellow-500'
  return 'bg-red-500'
}

function scoreWidth(score: number): string {
  // score is 0–5, convert to %
  const pct = Math.min(Math.max((score / 5) * 100, 0), 100)
  return `${pct.toFixed(1)}%`
}

export default function EvalScoreBar({ scores }: EvalScoreBarProps) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
      {/* Header row */}
      <div className="flex items-center justify-between mb-3">
        <span className="text-xs font-semibold uppercase tracking-wider text-gray-400">
          Memo Quality Score
        </span>
        <span className={`text-lg font-bold tabular-nums ${overallColor(scores.overall)}`}>
          {scores.overall.toFixed(1)}{' '}
          <span className="text-xs font-normal text-gray-500">/ 5.0</span>
        </span>
      </div>

      {/* Dimension bars */}
      <div className="flex flex-col gap-2">
        {DIMENSIONS.map(({ key, label }) => {
          const value = scores[key]
          const rationale = scores.rationale?.[key]
          return (
            <div key={key} title={rationale ?? ''}>
              <div className="flex items-center justify-between mb-0.5">
                <span className="text-xs text-gray-400 select-none">{label}</span>
                <span className={`text-xs font-semibold tabular-nums ${barColor(value).replace('bg-', 'text-')}`}>
                  {value.toFixed(1)}
                </span>
              </div>
              <div className="h-1.5 w-full bg-gray-700 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all duration-500 ${barColor(value)}`}
                  style={{ width: scoreWidth(value) }}
                />
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
