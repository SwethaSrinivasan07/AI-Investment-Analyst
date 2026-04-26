'use client'

import { useState, useEffect, useCallback, useRef } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import {
  getPortfolio, getMemos, getMe, addPosition, deletePosition, clearToken,
  getAlerts, getAlpacaStatus, importPortfolioCSV,
  type PortfolioResponse, type UserProfile, type Memo,
  type PortfolioAlert, type AlpacaStatus, type PortfolioOrder,
} from '@/lib/api'
import PortfolioTable from '@/components/PortfolioTable'
import AlertsPanel from '@/components/AlertsPanel'
import TradeConfirmModal, { type TradeProposal } from '@/components/TradeConfirmModal'

function SummarySkeleton() {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
      {[...Array(4)].map((_, i) => (
        <div key={i} className="bg-white border border-black/8 p-4 animate-pulse">
          <div className="h-2 bg-black/5 w-1/2 mb-3" />
          <div className="h-5 bg-black/5 w-3/4" />
        </div>
      ))}
    </div>
  )
}

function TableSkeleton() {
  return (
    <div className="bg-white border border-black/8 overflow-hidden animate-pulse">
      <div className="px-5 py-3 border-b border-black/8 bg-[#F6F3EE] flex gap-8">
        {[...Array(8)].map((_, i) => (
          <div key={i} className="h-2 bg-black/8 w-16" />
        ))}
      </div>
      {[...Array(6)].map((_, i) => (
        <div key={i} className="px-5 py-3.5 border-b border-black/5 flex items-center gap-6">
          <div className="flex flex-col gap-1.5 w-28">
            <div className="h-3 bg-black/5 w-16" />
            <div className="h-2 bg-black/5 w-24" />
          </div>
          {[...Array(6)].map((_, j) => (
            <div key={j} className="h-3 bg-black/5 w-16 ml-auto" />
          ))}
          <div className="h-5 bg-black/5 w-14" />
        </div>
      ))}
    </div>
  )
}

export default function PortfolioPage() {
  const router = useRouter()
  const fileInputRef = useRef<HTMLInputElement>(null)

  const [portfolio, setPortfolio] = useState<PortfolioResponse | null>(null)
  const [memos, setMemos] = useState<Memo[]>([])
  const [user, setUser] = useState<UserProfile | null>(null)
  const [alerts, setAlerts] = useState<PortfolioAlert[]>([])
  const [alpacaStatus, setAlpacaStatus] = useState<AlpacaStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [addForm, setAddForm] = useState({ ticker: '', shares: '', costBasis: '' })
  const [adding, setAdding] = useState(false)
  const [addError, setAddError] = useState<string | null>(null)

  const [importing, setImporting] = useState(false)
  const [importMsg, setImportMsg] = useState<string | null>(null)

  const [tradeProposal, setTradeProposal] = useState<TradeProposal | null>(null)

  const unreadCount = alerts.filter(a => !a.read).length

  const loadData = useCallback(async () => {
    try {
      const [portfolioData, userData, memosData, alertsData, alpacaData] = await Promise.all([
        getPortfolio(), getMe(), getMemos(), getAlerts(), getAlpacaStatus(),
      ])
      setPortfolio(portfolioData)
      setUser(userData)
      setMemos(memosData)
      setAlerts(alertsData)
      setAlpacaStatus(alpacaData)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to load portfolio'
      if (msg.includes('401') || msg.includes('Unauthorized')) {
        clearToken()
        router.replace('/auth/login')
      } else {
        setError(msg)
      }
    } finally {
      setLoading(false)
    }
  }, [router])

  useEffect(() => {
    const token = typeof window !== 'undefined' ? localStorage.getItem('alphalens_token') : null
    if (!token) { router.replace('/auth/login'); return }
    loadData()
  }, [router, loadData])

  function handleLogout() {
    clearToken()
    router.replace('/auth/login')
  }

  async function handleAdd() {
    const ticker = addForm.ticker.trim().toUpperCase()
    const shares = parseFloat(addForm.shares)
    const costBasis = parseFloat(addForm.costBasis)
    if (!ticker || isNaN(shares) || shares <= 0 || isNaN(costBasis) || costBasis <= 0) {
      setAddError('Please fill in all fields with valid values.')
      return
    }
    setAdding(true)
    setAddError(null)
    try {
      await addPosition({ ticker, shares, cost_basis: costBasis })
      setAddForm({ ticker: '', shares: '', costBasis: '' })
      setLoading(true)
      await loadData()
    } catch (err: unknown) {
      setAddError(err instanceof Error ? err.message : 'Failed to add position.')
    } finally {
      setAdding(false)
    }
  }

  async function handleDelete(id: string) {
    try {
      await deletePosition(id)
      setPortfolio((prev) => {
        if (!prev) return prev
        const newPositions = prev.positions.filter((p) => p.id !== id)
        const totalValue = newPositions.reduce((s, p) => s + p.market_value, 0)
        const totalCost = newPositions.reduce((s, p) => s + p.cost_value, 0)
        const totalGainLoss = totalValue - totalCost
        return {
          positions: newPositions,
          summary: {
            total_value: totalValue,
            total_cost: totalCost,
            total_gain_loss: totalGainLoss,
            total_gain_loss_pct: totalCost > 0 ? (totalGainLoss / totalCost) * 100 : 0,
            position_count: newPositions.length,
          },
        }
      })
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to remove position.')
    }
  }

  async function handleCSVImport(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    setImporting(true)
    setImportMsg(null)
    try {
      const result = await importPortfolioCSV(file)
      setImportMsg(`Imported ${result.imported} position${result.imported !== 1 ? 's' : ''} from ${file.name}.`)
      setLoading(true)
      await loadData()
    } catch (err: unknown) {
      setImportMsg(err instanceof Error ? err.message : 'Import failed.')
    } finally {
      setImporting(false)
      // reset file input so same file can be re-selected
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  function handleTradeConfirmed(order: PortfolioOrder) {
    setTradeProposal(null)
    // Silently reload portfolio + alerts in background
    loadData()
    // Show a brief success message via importMsg reuse
    setImportMsg(
      `Order submitted: ${order.side.toUpperCase()} ${order.qty}× ${order.ticker} — ${order.status}`
    )
  }

  return (
    <div className="min-h-screen">
      <nav className="sticky top-0 z-10 bg-white border-b border-black/8">
        <div className="max-w-[1000px] mx-auto px-6">
          <div className="flex items-center justify-between h-12">
            <div className="flex items-center gap-7">
              <div className="flex items-center gap-2">
                <div className="w-6 h-6 bg-[#2E2A47] flex items-center justify-center">
                  <span className="text-white text-[9px] font-bold tracking-wider">AL</span>
                </div>
                <span className="text-[13px] font-medium text-[#121212] tracking-tight">AlphaLens</span>
              </div>
              <div className="hidden sm:flex items-center gap-5">
                <Link href="/dashboard" className="text-[12px] text-[#5C5C5C] hover:text-[#121212] transition-colors">
                  Memos
                </Link>
                <Link href="/portfolio" className="relative text-[12px] font-medium text-[#2E2A47] border-b border-[#2E2A47] pb-0.5">
                  Portfolio
                  {unreadCount > 0 && (
                    <span className="absolute -top-1.5 -right-4 text-[9px] bg-red-500 text-white rounded-full px-1 leading-none py-0.5">
                      {unreadCount}
                    </span>
                  )}
                </Link>
                <Link href="/backtests" className="text-[12px] text-[#5C5C5C] hover:text-[#121212] transition-colors">
                  Backtests
                </Link>
                <Link href="/settings" className="text-[12px] text-[#5C5C5C] hover:text-[#121212] transition-colors">
                  Settings
                </Link>
              </div>
            </div>
            <div className="flex items-center gap-5">
              {user && <span className="hidden sm:block text-[12px] text-[#5C5C5C]">{user.email}</span>}
              <button onClick={handleLogout} className="text-[12px] text-[#5C5C5C] hover:text-[#121212] transition-colors">
                Sign out
              </button>
            </div>
          </div>
        </div>
      </nav>

      <div className="max-w-[1000px] mx-auto px-6 py-8">
        {/* Page header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="font-serif text-[28px] font-normal text-[#121212] leading-tight">Portfolio</h1>
            <p className="text-[13px] text-[#5C5C5C] mt-1">
              {portfolio
                ? `${portfolio.summary.position_count} position${portfolio.summary.position_count !== 1 ? 's' : ''} · live prices · AI signals`
                : 'Live prices and AI-powered position signals'}
            </p>
          </div>
          <div className="flex items-center gap-2">
            {/* CSV import */}
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv"
              className="hidden"
              onChange={handleCSVImport}
            />
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={importing}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-white border border-black/8 hover:border-black/20 text-[#5C5C5C] hover:text-[#121212] text-[12px] font-medium transition-colors disabled:opacity-50"
              title="Import positions from a CSV (Schwab, Robinhood, or standard format)"
            >
              {importing ? (
                <span className="w-3.5 h-3.5 border-2 border-current border-t-transparent rounded-full animate-spin" />
              ) : (
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
                </svg>
              )}
              {importing ? 'Importing…' : 'Import CSV'}
            </button>

            {!loading && (
              <button
                onClick={() => { setLoading(true); setError(null); loadData() }}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-white border border-black/8 hover:border-black/20 text-[#5C5C5C] hover:text-[#121212] text-[12px] font-medium transition-colors"
              >
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                </svg>
                Refresh
              </button>
            )}
          </div>
        </div>

        {/* Status / import message */}
        {importMsg && (
          <div className="mb-4 px-4 py-2.5 bg-white border border-black/8 text-[13px] text-[#2E2A47] flex items-center justify-between">
            <span>{importMsg}</span>
            <button onClick={() => setImportMsg(null)} className="text-gray-400 hover:text-gray-700 ml-4 text-xs">✕</button>
          </div>
        )}

        {error && (
          <div className="mb-5 px-4 py-3 bg-[#A14A44]/8 border border-[#A14A44]/20 text-[#A14A44] text-[13px] flex items-center justify-between">
            <span>{error}</span>
            <button onClick={() => setError(null)} className="text-[#A14A44]/60 hover:text-[#A14A44] ml-4">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        )}

        {/* Alpaca mode banner */}
        {!loading && alpacaStatus && (
          <div className={`mb-4 px-4 py-2 border text-[11px] flex items-center gap-2 ${
            alpacaStatus.mode === 'live'
              ? 'bg-red-50 border-red-200 text-red-700'
              : alpacaStatus.configured
              ? 'bg-emerald-50 border-emerald-200 text-emerald-700'
              : 'bg-gray-50 border-black/8 text-gray-500'
          }`}>
            <span className={`w-1.5 h-1.5 rounded-full ${
              alpacaStatus.mode === 'live' ? 'bg-red-500' : alpacaStatus.configured ? 'bg-emerald-500' : 'bg-gray-400'
            }`} />
            {alpacaStatus.mode === 'live'
              ? 'Connected to Alpaca — LIVE trading enabled'
              : alpacaStatus.configured
              ? 'Connected to Alpaca paper trading'
              : 'Alpaca not configured — orders will be logged only (add ALPACA_API_KEY to .env)'}
          </div>
        )}

        {loading ? (
          <div className="space-y-4">
            <div className="flex items-center gap-2 mb-1">
              <span className="w-3 h-3 border-2 border-[#2E2A47] border-t-transparent rounded-full animate-spin shrink-0" />
              <p className="text-[12px] text-[#5C5C5C]">Fetching live prices and AI signals — usually takes 10–15 seconds</p>
            </div>
            <SummarySkeleton />
            <TableSkeleton />
          </div>
        ) : portfolio ? (
          <div className="space-y-4">
            <PortfolioTable
              positions={portfolio.positions}
              summary={portfolio.summary}
              memos={memos}
              onDelete={handleDelete}
              onTrade={(ticker, side, qty, rationale) =>
                setTradeProposal({ ticker, side, qty, rationale })
              }
            />

            {/* Add position */}
            <div className="bg-white border border-black/8 px-5 py-4">
              <p className="text-[11px] font-medium text-[#5C5C5C] uppercase tracking-widest mb-3">Add Position</p>
              <div className="flex flex-wrap gap-2 items-end">
                <div className="flex flex-col gap-1">
                  <label className="text-[10px] text-[#5C5C5C] uppercase tracking-widest">Ticker</label>
                  <input
                    value={addForm.ticker}
                    onChange={(e) => setAddForm((f) => ({ ...f, ticker: e.target.value.toUpperCase().slice(0, 6) }))}
                    onKeyDown={(e) => { if (e.key === 'Enter') handleAdd() }}
                    placeholder="AAPL"
                    disabled={adding}
                    className="w-24 px-2 py-1.5 bg-[#F6F3EE] border border-black/8 text-[#121212] text-[13px] focus:outline-none focus:border-[#2E2A47]/40 tracking-widest uppercase placeholder-[#5C5C5C]/40 disabled:opacity-50"
                  />
                </div>
                <div className="flex flex-col gap-1">
                  <label className="text-[10px] text-[#5C5C5C] uppercase tracking-widest">Shares</label>
                  <input
                    type="number"
                    value={addForm.shares}
                    onChange={(e) => setAddForm((f) => ({ ...f, shares: e.target.value }))}
                    onKeyDown={(e) => { if (e.key === 'Enter') handleAdd() }}
                    placeholder="10"
                    min="0"
                    disabled={adding}
                    className="w-24 px-2 py-1.5 bg-[#F6F3EE] border border-black/8 text-[#121212] text-[13px] focus:outline-none focus:border-[#2E2A47]/40 placeholder-[#5C5C5C]/40 disabled:opacity-50"
                  />
                </div>
                <div className="flex flex-col gap-1">
                  <label className="text-[10px] text-[#5C5C5C] uppercase tracking-widest">Cost Basis ($)</label>
                  <input
                    type="number"
                    value={addForm.costBasis}
                    onChange={(e) => setAddForm((f) => ({ ...f, costBasis: e.target.value }))}
                    onKeyDown={(e) => { if (e.key === 'Enter') handleAdd() }}
                    placeholder="150.00"
                    min="0"
                    step="0.01"
                    disabled={adding}
                    className="w-32 px-2 py-1.5 bg-[#F6F3EE] border border-black/8 text-[#121212] text-[13px] focus:outline-none focus:border-[#2E2A47]/40 placeholder-[#5C5C5C]/40 disabled:opacity-50"
                  />
                </div>
                <button
                  onClick={handleAdd}
                  disabled={adding || !addForm.ticker || !addForm.shares || !addForm.costBasis}
                  className="px-4 py-1.5 bg-[#2E2A47] hover:bg-[#1E1A35] disabled:bg-black/8 disabled:text-[#5C5C5C]/40 disabled:cursor-not-allowed text-white text-[13px] font-medium transition-colors"
                >
                  {adding ? (
                    <span className="flex items-center gap-1.5">
                      <span className="w-3 h-3 border-2 border-white/40 border-t-white rounded-full animate-spin" />
                      Adding...
                    </span>
                  ) : 'Add'}
                </button>
              </div>
              {addError && <p className="mt-2 text-[12px] text-[#A14A44]">{addError}</p>}
              <p className="mt-2 text-[10px] text-[#5C5C5C]/60">
                Or import all positions at once via CSV (Schwab, Robinhood, or standard format supported)
              </p>
            </div>

            {/* Alerts panel */}
            <div>
              <h2 className="font-serif text-[16px] text-[#121212] mb-3">
                AI Monitor Alerts
                {unreadCount > 0 && (
                  <span className="ml-2 text-[11px] bg-red-500 text-white rounded-full px-1.5 py-0.5 font-sans">
                    {unreadCount} new
                  </span>
                )}
              </h2>
              <AlertsPanel alerts={alerts} onAlertsChange={setAlerts} />
            </div>
          </div>
        ) : (
          !error && (
            <div className="flex flex-col items-center justify-center py-28 text-center">
              <div className="w-12 h-12 bg-white border border-black/8 flex items-center justify-center mb-4">
                <svg className="w-6 h-6 text-[#5C5C5C]/30" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                    d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                </svg>
              </div>
              <h3 className="font-serif text-[18px] text-[#121212] mb-1">No positions found</h3>
              <p className="text-[#5C5C5C] text-[13px] max-w-xs">
                Add positions manually or import a broker CSV to get started.
              </p>
            </div>
          )
        )}

        <p className="mt-10 text-center text-[11px] text-[#5C5C5C]/50">
          For educational use only. Not financial advice.
        </p>
      </div>

      {/* Trade confirmation modal */}
      {tradeProposal && (
        <TradeConfirmModal
          proposal={tradeProposal}
          alpacaStatus={alpacaStatus}
          onConfirm={handleTradeConfirmed}
          onDismiss={() => setTradeProposal(null)}
        />
      )}
    </div>
  )
}
