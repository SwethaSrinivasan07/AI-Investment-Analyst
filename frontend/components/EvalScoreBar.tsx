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
  if (score >= 4) return 'text-[#2F6B4F]'
  if (score >= 3) return 'text-[#6B7280]'
  return 'text-[#A14A44]'
}

function barColor(score: number): string {
  if (score >= 4) return 'bg-[#2F6B4F]'
  if (score >= 3) return 'bg-[#6B7280]'
  return 'bg-[#A14A44]'
}

function scoreTextColor(score: number): string {
  if (score >= 4) return 'text-[#2F6B4F]'
  if (score >= 3) return 'text-[#6B7280]'
  return 'text-[#A14A44]'
}

function scoreWidth(score: number): string {
  const pct = Math.min(Math.max((score / 5) * 100, 0), 100)
  return `${pct.toFixed(1)}%`
}

export default function EvalScoreBar({ scores }: EvalScoreBarProps) {
  return (
    <div className="bg-white border border-black/8 p-4">
      <div className="flex items-center justify-between mb-3">
        <span className="text-[11px] font-medium uppercase tracking-widest text-[#5C5C5C]">
          Memo Quality
        </span>
        <span className={`text-[15px] font-medium tabular-nums ${overallColor(scores.overall)}`}>
          {scores.overall.toFixed(1)}{' '}
          <span className="text-[12px] font-normal text-[#5C5C5C]">/ 5.0</span>
        </span>
      </div>

      <div className="flex flex-col gap-2.5">
        {DIMENSIONS.map(({ key, label }) => {
          const value = scores[key]
          const rationale = scores.rationale?.[key]
          return (
            <div key={key} title={rationale ?? ''}>
              <div className="flex items-center justify-between mb-1">
                <span className="text-[12px] text-[#5C5C5C]">{label}</span>
                <span className={`text-[12px] font-medium tabular-nums ${scoreTextColor(value)}`}>
                  {value.toFixed(1)}
                </span>
              </div>
              <div className="h-0.5 w-full bg-black/8 overflow-hidden">
                <div
                  className={`h-full transition-all duration-500 ${barColor(value)}`}
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
