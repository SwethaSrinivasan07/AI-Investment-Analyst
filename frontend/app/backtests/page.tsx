'use client'

import { useState, useEffect, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import {
  runBacktest,
  getBacktests,
  clearToken,
  type BacktestResult,
  type BacktestMetrics,
} from '@/lib/api'
import BacktestChart from '@/components/BacktestChart'

const STRATEGIES = [
  { value: 'momentum', label: 'Momentum' },
  { value: 'value', label: 'Value' },
  { value: 'growth', label: 'Growth' },
  { value: 'dividend', label: 'Dividend' },
]

const SECTORS = [
  'Technology', 'Healthcare', 'Financials', 'Consumer Discretionary',
  'Consumer Staples', 'Industrials', 'Energy', 'Materials',
  'Real Estate', 'Utilities', 'Communication Services',
]

const PERIODS = [
  { value: '1y', label: '1 Year' },
  { value: '2y', label: '2 Years' },
]

interface MetricCardProps {
  label: string
  value: string
  positive?: boolean
  subtitle?: string
  inlineNote?: string
  tooltip?: string
}

function MetricCard({ label, value, positive, subtitle, inlineNote, tooltip }: MetricCardProps) {
  const valueColor =
    positive === undefined ? 'text-[#121212]' : positive ? 'text-[#2F6B4F]' : 'text-[#A14A44]'
  return (
    <div className="bg-white border border-black/8 px-4 py-3">
      <p className="text-[11px] font-medium text-[#5C5C5C] uppercase tracking-widest mb-1">{label}</p>
      <div className="flex items-baseline gap-1.5 flex-wrap">
        <p className={`text-[20px] font-light tabular-nums leading-tight ${valueColor}`} title={tooltip}>{value}</p>
        {tooltip && (
          <span className="text-[11px] text-[#5C5C5C] cursor-help underline decoration-dotted" title={tooltip}>?</span>
        )}
      </div>
      {subtitle && <p className="text-[11px] text-[#5C5C5C] mt-0.5">{subtitle}</p>}
      {inlineNote && <p className="text-[11px] text-[#6B7280] mt-1 leading-snug">{inlineNote}</p>}
    </div>
  )
}

function formatPct(v: number, decimals = 1): string {
  return `${v >= 0 ? '+' : ''}${v.toFixed(decimals)}%`
}

interface MetricCardConfig {
  label: string; value: string; positive?: boolean; subtitle?: string; inlineNote?: string; tooltip?: string
}

function metricsCards(metrics: BacktestMetrics, period: string, strategy: string, sector: string): MetricCardConfig[] {
  const rawSharpe = metrics.sharpe_ratio
  const sharpeDisplay = rawSharpe > 5.0 ? '5.0+' : rawSharpe.toFixed(2)
  const sharpeTooltip = rawSharpe > 5.0 ? 'Extreme values often reflect data artifacts in short backtests.' : undefined
  const sharpeInlineNote =
    period === '1y' && strategy === 'momentum' && sector === 'Technology' && rawSharpe > 2.0
      ? '1y tech momentum captures the AI rally — try 2y for context'
      : undefined
  return [
    { label: 'Cumulative Return', value: formatPct(metrics.cumulative_return_pct), positive: metrics.cumulative_return_pct >= 0 },
    { label: 'Annualized Return', value: formatPct(metrics.annualized_return_pct), positive: metrics.annualized_return_pct >= 0 },
    { label: 'Sharpe Ratio', value: sharpeDisplay, positive: metrics.sharpe_ratio >= 1, subtitle: '≥ 1.0 is good', inlineNote: sharpeInlineNote, tooltip: sharpeTooltip },
    { label: 'Max Drawdown', value: formatPct(metrics.max_drawdown_pct), positive: false, subtitle: 'Peak-to-trough' },
    { label: 'Win Rate vs SPY', value: `${metrics.win_rate_pct.toFixed(1)}%`, positive: metrics.win_rate_pct >= 50, subtitle: 'Weekly periods' },
    { label: 'Alpha vs SPY', value: formatPct(metrics.alpha_vs_spy_pct), positive: metrics.alpha_vs_spy_pct >= 0, subtitle: 'Cumulative excess return' },
  ]
}

interface HistoryRowProps {
  result: BacktestResult
  onSelect: (r: BacktestResult) => void
}

function HistoryRow({ result, onSelect }: HistoryRowProps) {
  const ret = result.metrics?.cumulative_return_pct ?? 0
  const retColor = ret >= 0 ? 'text-[#2F6B4F]' : 'text-[#A14A44]'
  const label = `${result.strategy.charAt(0).toUpperCase() + result.strategy.slice(1)} · ${result.sector} · ${result.period.toUpperCase()}`
  const date = new Date(result.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
  return (
    <button
      onClick={() => onSelect(result)}
      className="w-full flex items-center justify-between px-3 py-2.5 bg-white border border-black/8 hover:border-black/20 transition-colors text-left"
    >
      <div>
        <p className="text-[12px] font-medium text-[#121212]">{label}</p>
        <p className="text-[11px] text-[#5C5C5C] mt-0.5">{date}</p>
      </div>
      <span className={`text-[12px] font-medium tabular-nums ${retColor}`}>{formatPct(ret)}</span>
    </button>
  )
}

export default function BacktestsPage() {
  const router = useRouter()
  const [strategy, setStrategy] = useState('momentum')
  const [sector, setSector] = useState('Technology')
  const [period, setPeriod] = useState('1y')
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<BacktestResult | null>(null)
  const [history, setHistory] = useState<BacktestResult[]>([])
  const [historyLoading, setHistoryLoading] = useState(true)
  const [methodologyOpen, setMethodologyOpen] = useState(false)

  useEffect(() => {
    const token = typeof window !== 'undefined' ? localStorage.getItem('alphalens_token') : null
    if (!token) router.replace('/auth/login')
  }, [router])

  const loadHistory = useCallback(async () => {
    setHistoryLoading(true)
    try {
      const data = await getBacktests()
      setHistory(data)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : ''
      if (msg.includes('401') || msg.includes('Unauthorized')) { clearToken(); router.replace('/auth/login') }
    } finally {
      setHistoryLoading(false)
    }
  }, [router])

  useEffect(() => { loadHistory() }, [loadHistory])

  async function handleRun() {
    setError(null); setRunning(true); setResult(null)
    try {
      const data = await runBacktest(strategy, sector, period)
      setResult(data)
      loadHistory()
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Backtest failed'
      if (msg.includes('401') || msg.includes('Unauthorized')) { clearToken(); router.replace('/auth/login') }
      else setError(msg)
    } finally {
      setRunning(false)
    }
  }

  function handleSelectHistory(r: BacktestResult) {
    setResult(r); setStrategy(r.strategy); setSector(r.sector); setPeriod(r.period)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const selectedStrategyLabel = STRATEGIES.find((s) => s.value === (result?.strategy ?? strategy))?.label ?? strategy
  const selectedSectorLabel = result?.sector ?? sector

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
                <Link href="/dashboard" className="text-[12px] text-[#5C5C5C] hover:text-[#121212] transition-colors">Memos</Link>
                <Link href="/portfolio" className="text-[12px] text-[#5C5C5C] hover:text-[#121212] transition-colors">Portfolio</Link>
                <span className="text-[12px] font-medium text-[#2E2A47] border-b border-[#2E2A47] pb-0.5">Backtests</span>
              </div>
            </div>
            <button
              onClick={() => { clearToken(); router.replace('/auth/login') }}
              className="text-[12px] text-[#5C5C5C] hover:text-[#121212] transition-colors"
            >
              Sign out
            </button>
          </div>
        </div>
      </nav>

      <div className="max-w-[1000px] mx-auto px-6 py-8">
        <div className="mb-8">
          <h1 className="font-serif text-[28px] font-normal text-[#121212] leading-tight">Strategy Performance</h1>
          <p className="text-[13px] text-[#5C5C5C] mt-1">Historical simulation of each strategy across sectors.</p>
        </div>

        <div className="grid grid-cols-1 xl:grid-cols-4 gap-5">
          {/* Left panel */}
          <div className="xl:col-span-1 space-y-4">
            <div className="bg-white border border-black/8 p-4">
              <h2 className="text-[11px] font-medium text-[#5C5C5C] uppercase tracking-widest mb-4">Configure</h2>
              <div className="space-y-3">
                <div>
                  <label className="block text-[11px] text-[#5C5C5C] mb-1.5 uppercase tracking-wider">Strategy</label>
                  <select
                    value={strategy}
                    onChange={(e) => setStrategy(e.target.value)}
                    disabled={running}
                    className="w-full bg-white border border-black/8 px-3 py-2 text-[13px] text-[#121212] focus:outline-none focus:ring-1 focus:ring-[#2E2A47] disabled:opacity-50"
                  >
                    {STRATEGIES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-[11px] text-[#5C5C5C] mb-1.5 uppercase tracking-wider">Sector</label>
                  <select
                    value={sector}
                    onChange={(e) => setSector(e.target.value)}
                    disabled={running}
                    className="w-full bg-white border border-black/8 px-3 py-2 text-[13px] text-[#121212] focus:outline-none focus:ring-1 focus:ring-[#2E2A47] disabled:opacity-50"
                  >
                    {SECTORS.map((s) => <option key={s} value={s}>{s}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-[11px] text-[#5C5C5C] mb-1.5 uppercase tracking-wider">Period</label>
                  <div className="flex gap-1.5">
                    {PERIODS.map((p) => (
                      <button
                        key={p.value}
                        onClick={() => setPeriod(p.value)}
                        disabled={running}
                        className={`flex-1 py-1.5 text-[13px] font-medium transition-colors disabled:opacity-50 ${
                          period === p.value
                            ? 'bg-[#2E2A47] text-white'
                            : 'bg-white border border-black/8 text-[#5C5C5C] hover:border-black/20'
                        }`}
                      >
                        {p.label}
                      </button>
                    ))}
                  </div>
                </div>
                <button
                  onClick={handleRun}
                  disabled={running}
                  className="w-full py-2 bg-[#2E2A47] hover:bg-[#1E1A35] disabled:opacity-50 disabled:cursor-not-allowed text-white text-[13px] font-medium transition-colors flex items-center justify-center gap-2"
                >
                  {running ? (
                    <><span className="w-3.5 h-3.5 border-2 border-white/40 border-t-white rounded-full animate-spin" />Running...</>
                  ) : 'Run Backtest'}
                </button>
                {error && (
                  <p className="text-[12px] text-[#A14A44] bg-[#A14A44]/8 px-3 py-2 border border-[#A14A44]/20">{error}</p>
                )}
              </div>
            </div>

            <div className="bg-white border border-black/8 p-4">
              <h2 className="text-[11px] font-medium text-[#5C5C5C] uppercase tracking-widest mb-3">Recent</h2>
              {historyLoading ? (
                <p className="text-[12px] text-[#5C5C5C]/50">Loading...</p>
              ) : history.length === 0 ? (
                <p className="text-[12px] text-[#5C5C5C]">No backtests run yet.</p>
              ) : (
                <div className="space-y-1.5">
                  {history.slice(0, 8).map((r) => (
                    <HistoryRow key={r.id} result={r} onSelect={handleSelectHistory} />
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Right panel */}
          <div className="xl:col-span-3 space-y-4">
            {running && (
              <div className="bg-white border border-black/8 p-12 flex flex-col items-center justify-center gap-4">
                <span className="w-6 h-6 border-2 border-[#2E2A47] border-t-transparent rounded-full animate-spin" />
                <div className="text-center">
                  <p className="text-[#121212] font-medium text-[13px]">Simulating strategy performance...</p>
                  <p className="text-[#5C5C5C] text-[12px] mt-1">Downloading prices and running weekly rebalancing. This may take 10–30 seconds.</p>
                </div>
              </div>
            )}

            {!running && result && (
              <>
                <div className="flex items-center justify-between">
                  <div>
                    <h2 className="font-serif text-[18px] text-[#121212]">
                      {selectedStrategyLabel} · {selectedSectorLabel}
                    </h2>
                    <p className="text-[12px] text-[#5C5C5C] mt-0.5">
                      {result.period === '1y' ? '1-year' : '2-year'} backtest · equal-weight top-3 picks, weekly rebalance
                    </p>
                  </div>
                  <span className="text-[11px] text-[#5C5C5C]">
                    {new Date(result.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
                  </span>
                </div>

                <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                  {metricsCards(result.metrics, result.period, result.strategy, result.sector).map((m) => (
                    <MetricCard key={m.label} {...m} />
                  ))}
                </div>

                {result.metrics.sharpe_ratio > 2.5 && (
                  <div className="bg-black/[0.03] border border-black/8 px-4 py-3">
                    <p className="text-[12px] text-[#5C5C5C] leading-relaxed">
                      <strong className="text-[#121212] font-medium">Unusually high Sharpe ratio.</strong>{' '}
                      A Sharpe above 2.5 typically reflects a short, exceptional market period rather than a repeatable edge.
                      The 1-year momentum/technology lookback captures the 2024–2025 AI infrastructure rally.
                      Try the 2-year period for a more conservative estimate.
                    </p>
                  </div>
                )}

                <div className="bg-white border border-black/8 p-5">
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="text-[11px] font-medium text-[#5C5C5C] uppercase tracking-widest">
                      Indexed Performance (Base = 100)
                    </h3>
                    <span className="text-[11px] text-[#5C5C5C]">Weekly sampled</span>
                  </div>
                  <BacktestChart
                    data={result.chart_data}
                    strategyLabel={selectedStrategyLabel}
                    sectorLabel={selectedSectorLabel}
                  />
                </div>

                <div className="bg-white border border-black/8 overflow-hidden">
                  <button
                    onClick={() => setMethodologyOpen((o) => !o)}
                    className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-black/[0.02] transition-colors"
                  >
                    <span className="text-[12px] font-medium text-[#5C5C5C]">Simulation Methodology &amp; Limitations</span>
                    <svg
                      className={`w-3.5 h-3.5 text-[#5C5C5C] transition-transform duration-150 ${methodologyOpen ? 'rotate-180' : ''}`}
                      fill="none" viewBox="0 0 24 24" stroke="currentColor"
                    >
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                    </svg>
                  </button>
                  {methodologyOpen && (
                    <div className="px-4 pb-4 pt-2 border-t border-black/8">
                      <ul className="text-[12px] text-[#5C5C5C] space-y-1.5 leading-relaxed">
                        <li><span className="text-[#121212] font-medium">Strategy:</span> Equal-weight top 3 picks by price momentum, rebalanced weekly</li>
                        <li><span className="text-[#121212] font-medium">Signals:</span> Price-only (1M + 3M returns). Fundamental signals are NOT point-in-time.</li>
                        <li><span className="text-[#121212] font-medium">Benchmark:</span> SPY total return, indexed to 100 at start</li>
                        <li><span className="text-[#121212] font-medium">Survivorship bias:</span> Universe is current S&amp;P 500 constituents — past delisted stocks excluded</li>
                        <li><span className="text-[#121212] font-medium">Transaction costs:</span> Not modeled (0 bps assumed — optimistic)</li>
                        <li>Short periods (1y) are highly sensitive to start/end date selection</li>
                        <li>Past performance does not predict future results</li>
                      </ul>
                    </div>
                  )}
                </div>

                <div className="border border-black/8 px-4 py-3 bg-[#F6F3EE]">
                  <p className="text-[11px] text-[#5C5C5C]">
                    <strong className="font-medium">Disclaimer:</strong> For educational use only. Not financial advice.
                  </p>
                </div>
              </>
            )}

            {!running && !result && (
              <div className="bg-white border border-black/8 p-16 flex flex-col items-center justify-center text-center gap-3">
                <div className="w-10 h-10 bg-[#F6F3EE] border border-black/8 flex items-center justify-center mb-2">
                  <svg className="w-5 h-5 text-[#5C5C5C]/30" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                      d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                  </svg>
                </div>
                <p className="text-[#121212] font-medium text-[13px]">No backtest selected</p>
                <p className="text-[#5C5C5C] text-[12px] max-w-xs">
                  Configure a strategy and sector, then click{' '}
                  <span className="text-[#2E2A47] font-medium">Run Backtest</span>.
                </p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
