'use client'

import { useState } from 'react'
import { placeOrder, PortfolioOrder, AlpacaStatus } from '@/lib/api'

export interface TradeProposal {
  ticker: string
  side: 'buy' | 'sell'
  qty: number
  rationale: string
}

interface Props {
  proposal: TradeProposal
  alpacaStatus: AlpacaStatus | null
  onConfirm: (order: PortfolioOrder) => void
  onDismiss: () => void
}

export default function TradeConfirmModal({ proposal, alpacaStatus, onConfirm, onDismiss }: Props) {
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const isPaper = alpacaStatus?.configured && alpacaStatus.mode === 'paper'
  const isLive = alpacaStatus?.configured && alpacaStatus.mode === 'live'

  async function handleConfirm() {
    setSubmitting(true)
    setError(null)
    try {
      const order = await placeOrder(proposal.ticker, proposal.side, proposal.qty, proposal.rationale)
      onConfirm(order)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Order failed')
      setSubmitting(false)
    }
  }

  const actionColor = proposal.side === 'buy' ? 'text-emerald-700' : 'text-red-700'
  const actionBg    = proposal.side === 'buy' ? 'bg-emerald-600 hover:bg-emerald-700' : 'bg-red-600 hover:bg-red-700'

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="bg-[#F6F3EE] border border-black/8 w-full max-w-sm p-6 space-y-5">

        {/* Header */}
        <div className="flex items-start justify-between">
          <div>
            <p className="text-xs uppercase tracking-widest text-gray-500 mb-1">AI Trade Signal</p>
            <h2 className="font-serif text-xl text-[#2E2A47]">
              <span className={`font-semibold ${actionColor}`}>
                {proposal.side === 'buy' ? 'Buy' : 'Sell'}
              </span>{' '}
              {proposal.qty} × {proposal.ticker}
            </h2>
          </div>
          <button onClick={onDismiss} className="text-gray-400 hover:text-gray-700 text-lg leading-none mt-0.5">
            ✕
          </button>
        </div>

        {/* Rationale */}
        <div className="border-l-2 border-[#2E2A47]/20 pl-4">
          <p className="text-xs text-gray-500 mb-0.5">Why this trade</p>
          <p className="text-sm text-gray-800 leading-relaxed">{proposal.rationale}</p>
        </div>

        {/* Execution context */}
        <div className="bg-white border border-black/8 p-3 space-y-1">
          <div className="flex justify-between text-xs">
            <span className="text-gray-500">Order type</span>
            <span className="font-medium text-gray-900">Market</span>
          </div>
          <div className="flex justify-between text-xs">
            <span className="text-gray-500">Quantity</span>
            <span className="font-medium text-gray-900">{proposal.qty} shares</span>
          </div>
          <div className="flex justify-between text-xs">
            <span className="text-gray-500">Execution</span>
            <span className={`font-medium ${isLive ? 'text-red-600' : 'text-emerald-600'}`}>
              {isLive ? 'Live account' : isPaper ? 'Paper trading' : 'Simulated (no broker)'}
            </span>
          </div>
        </div>

        {isLive && (
          <div className="text-xs bg-red-50 border border-red-200 text-red-700 p-3">
            This will execute with real money on your live Alpaca account.
          </div>
        )}

        <p className="text-[10px] text-gray-400 leading-relaxed">
          For educational use only. Not financial advice. AlphaLens AI signals may be incorrect.
          Always review before executing.
        </p>

        {error && <p className="text-xs text-red-600">{error}</p>}

        {/* Actions */}
        <div className="flex gap-3">
          <button
            onClick={onDismiss}
            className="flex-1 py-2 border border-black/8 text-sm text-gray-700 hover:bg-black/4 transition-colors"
          >
            Dismiss
          </button>
          <button
            onClick={handleConfirm}
            disabled={submitting}
            className={`flex-1 py-2 text-sm text-white transition-colors disabled:opacity-50 ${actionBg}`}
          >
            {submitting ? 'Submitting…' : `Confirm ${proposal.side === 'buy' ? 'Buy' : 'Sell'}`}
          </button>
        </div>
      </div>
    </div>
  )
}
