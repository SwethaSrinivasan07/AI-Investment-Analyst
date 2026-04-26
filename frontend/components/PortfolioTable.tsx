'use client'

import { useState, useMemo } from 'react'
import Link from 'next/link'
import type { PortfolioPosition, PortfolioSummary, Memo } from '@/lib/api'

interface PortfolioTableProps {
  positions: PortfolioPosition[]
  summary: PortfolioSummary
  memos?: Memo[]
  onDelete?: (id: string) => Promise<void>
  onTrade?: (ticker: string, side: 'buy' | 'sell', qty: number, rationale: string) => void
}

const signalStyles: Record<string, string> = {
  Add:  'bg-[#2F6B4F]/8 text-[#2F6B4F] border border-[#2F6B4F]/20',
  Hold: 'bg-black/5 text-[#5C5C5C] border border-black/8',
  Trim: 'bg-[#A14A44]/8 text-[#A14A44] border border-[#A14A44]/20',
}

function formatCurrency(value: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency', currency: 'USD',
    minimumFractionDigits: 2, maximumFractionDigits: 2,
  }).format(value)
}

function formatPct(value: number): string {
  return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`
}

function GainLossCell({ value, pct }: { value: number; pct: number }) {
  const color = value >= 0 ? 'text-[#2F6B4F]' : 'text-[#A14A44]'
  return (
    <div className={`text-right ${color}`}>
      <div className="font-medium text-[13px]">{formatCurrency(value)}</div>
      <div className="text-[11px] opacity-75">{formatPct(pct)}</div>
    </div>
  )
}

function ChangePctCell({ value }: { value: number }) {
  const color = value >= 0 ? 'text-[#2F6B4F]' : 'text-[#A14A44]'
  return <span className={`font-medium text-[13px] ${color}`}>{formatPct(value)}</span>
}

function SignalBadge({ signal, rationale }: { signal: string; rationale: string }) {
  const cls = signalStyles[signal] ?? signalStyles['Hold']
  return (
    <div className="flex flex-col items-start gap-1 min-w-[90px]">
      <span className={`inline-block text-[11px] font-medium px-1.5 py-0.5 ${cls}`}>
        {signal}
      </span>
      {rationale && (
        <span className="text-[11px] text-[#5C5C5C] leading-snug max-w-[200px]">{rationale}</span>
      )}
    </div>
  )
}

export default function PortfolioTable({ positions, summary, memos = [], onDelete, onTrade }: PortfolioTableProps) {
  const [deleting, setDeleting] = useState<string | null>(null)

  const summaryGainPositive = summary.total_gain_loss >= 0

  // Index most recent memo per ticker (memos arrive newest-first from API)
  const memoByTicker = useMemo(() => {
    const map: Record<string, Memo> = {}
    for (const memo of memos) {
      if (!map[memo.ticker]) map[memo.ticker] = memo
    }
    return map
  }, [memos])

  async function handleDelete(id: string) {
    if (!onDelete) return
    setDeleting(id)
    try {
      await onDelete(id)
    } finally {
      setDeleting(null)
    }
  }

  return (
    <div className="space-y-4">
      {/* Summary bar */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {[
          { label: 'Total Value', value: formatCurrency(summary.total_value),        colored: false },
          { label: 'Total Cost',  value: formatCurrency(summary.total_cost),          colored: false },
          { label: 'Total P&L',  value: formatCurrency(summary.total_gain_loss),     colored: true  },
          { label: 'Return',     value: formatPct(summary.total_gain_loss_pct),       colored: true  },
        ].map(({ label, value, colored }) => (
          <div key={label} className="bg-white border border-black/8 px-4 py-3">
            <p className="text-[11px] font-medium text-[#5C5C5C] uppercase tracking-widest mb-1">{label}</p>
            <p className={`text-[20px] font-light tabular-nums leading-tight ${
              colored ? (summaryGainPositive ? 'text-[#2F6B4F]' : 'text-[#A14A44]') : 'text-[#121212]'
            }`}>
              {value}
            </p>
          </div>
        ))}
      </div>

      {/* Positions table */}
      <div className="bg-white border border-black/8 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-[13px]">
            <thead>
              <tr className="border-b border-black/8 bg-[#F6F3EE]">
                <th className="text-left text-[11px] text-[#5C5C5C] font-medium uppercase tracking-widest px-5 py-3">Ticker</th>
                <th className="text-right text-[11px] text-[#5C5C5C] font-medium uppercase tracking-widest px-4 py-3">Shares</th>
                <th className="text-right text-[11px] text-[#5C5C5C] font-medium uppercase tracking-widest px-4 py-3">Cost</th>
                <th className="text-right text-[11px] text-[#5C5C5C] font-medium uppercase tracking-widest px-4 py-3">Price</th>
                <th className="text-right text-[11px] text-[#5C5C5C] font-medium uppercase tracking-widest px-4 py-3">Value</th>
                <th className="text-right text-[11px] text-[#5C5C5C] font-medium uppercase tracking-widest px-4 py-3">P&L</th>
                <th className="text-right text-[11px] text-[#5C5C5C] font-medium uppercase tracking-widest px-4 py-3">1D</th>
                <th className="text-left text-[11px] text-[#5C5C5C] font-medium uppercase tracking-widest px-4 py-3">Signal</th>
                <th className="w-8 px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-black/[0.04]">
              {positions.map((pos) => {
                const linkedMemo = memoByTicker[pos.ticker]
                return (
                  <tr key={pos.id} className="hover:bg-black/[0.02] transition-colors duration-75 group">
                    <td className="px-5 py-3">
                      <div className="font-medium text-[#121212] text-[13px]">{pos.ticker}</div>
                      <div className="text-[11px] text-[#5C5C5C] truncate max-w-[160px]">
                        {pos.company_name ?? '—'}
                      </div>
                      {linkedMemo && (
                        <Link
                          href={`/memo/${linkedMemo.id}`}
                          className="text-[11px] text-[#2E2A47] hover:underline leading-none"
                        >
                          View memo →
                        </Link>
                      )}
                    </td>
                    <td className="px-4 py-3 text-right text-[#5C5C5C] text-[13px]">
                      {pos.shares.toLocaleString()}
                    </td>
                    <td className="px-4 py-3 text-right text-[#5C5C5C] text-[13px]">
                      {formatCurrency(pos.cost_basis)}
                    </td>
                    <td className="px-4 py-3 text-right text-[#121212] font-medium text-[13px]">
                      {formatCurrency(pos.current_price)}
                    </td>
                    <td className="px-4 py-3 text-right text-[#5C5C5C] text-[13px]">
                      {formatCurrency(pos.market_value)}
                    </td>
                    <td className="px-4 py-3">
                      <GainLossCell value={pos.gain_loss} pct={pos.gain_loss_pct} />
                    </td>
                    <td className="px-4 py-3 text-right">
                      <ChangePctCell value={pos.price_change_1d_pct} />
                    </td>
                    <td className="px-4 py-3">
                      <div className="space-y-1.5">
                        <SignalBadge signal={pos.signal} rationale={pos.signal_rationale} />
                        {onTrade && (pos.signal === 'Add' || pos.signal === 'Trim') && (
                          <button
                            onClick={() => onTrade(
                              pos.ticker,
                              pos.signal === 'Add' ? 'buy' : 'sell',
                              pos.signal === 'Trim' ? Math.max(1, Math.round(pos.shares * 0.25)) : 1,
                              pos.signal_rationale,
                            )}
                            className="text-[10px] px-2 py-0.5 border border-[#2E2A47]/30 text-[#2E2A47] hover:bg-[#2E2A47] hover:text-white transition-colors"
                          >
                            Execute →
                          </button>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-right">
                      {onDelete && (
                        <button
                          onClick={() => handleDelete(pos.id)}
                          disabled={deleting === pos.id}
                          title="Remove position"
                          className="opacity-0 group-hover:opacity-100 text-[#5C5C5C]/40 hover:text-[#A14A44] disabled:cursor-not-allowed transition-all"
                        >
                          {deleting === pos.id ? (
                            <span className="w-3 h-3 border border-[#5C5C5C]/40 border-t-transparent rounded-full animate-spin inline-block" />
                          ) : (
                            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                            </svg>
                          )}
                        </button>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
