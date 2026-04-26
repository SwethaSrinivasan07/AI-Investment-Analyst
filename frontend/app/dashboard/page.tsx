'use client'

import { useState, useEffect, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import {
  getMemos,
  getMe,
  clearToken,
  deleteMemo,
  getMemoStats,
  type Memo,
  type UserProfile,
  type MemoStats,
} from '@/lib/api'
import MemoCard from '@/components/MemoCard'
import GenerateMemoModal from '@/components/GenerateMemoModal'

const EVAL_DIMS: { key: string; label: string }[] = [
  { key: 'data_grounding', label: 'Grounding' },
  { key: 'thesis_clarity', label: 'Clarity' },
  { key: 'risk_depth', label: 'Risk' },
  { key: 'valuation_rigor', label: 'Valuation' },
  { key: 'actionability', label: 'Action' },
]

interface SystemMetricsPanelProps {
  stats: MemoStats
}

function ScoreMiniBar({ score }: { score: number | null }) {
  const pct = score != null ? (score / 5) * 100 : 0
  return (
    <div className="flex items-center gap-1.5 w-full">
      <div className="flex-1 h-0.5 bg-black/8 overflow-hidden">
        <div
          className="h-full bg-[#2E2A47] transition-all duration-500"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-[11px] text-[#5C5C5C] w-6 text-right tabular-nums">
        {score != null ? score.toFixed(1) : '—'}
      </span>
    </div>
  )
}

function MetricChip({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="flex-1 min-w-[120px] bg-white border border-black/8 px-4 py-3">
      <p className="text-[11px] font-medium text-[#5C5C5C] uppercase tracking-widest mb-1">{label}</p>
      <p className="text-[20px] font-light text-[#121212] leading-tight tabular-nums">{value}</p>
      {sub && <p className="text-[11px] text-[#5C5C5C] mt-0.5">{sub}</p>}
    </div>
  )
}

function SystemMetricsPanel({ stats }: SystemMetricsPanelProps) {
  const tu = stats.token_usage
  const avgOverall = stats.avg_eval_scores['overall']
  const groundingPct = stats.grounding_rate_pct.toFixed(0)
  const avgScore = avgOverall != null ? avgOverall.toFixed(2) : '—'
  const costStr = tu.total_estimated_cost_usd != null ? `$${tu.total_estimated_cost_usd.toFixed(4)}` : '—'
  const cachePct = tu.cache_savings_pct != null ? `${tu.cache_savings_pct.toFixed(1)}% savings` : null
  const tokenRow = [
    `${tu.total_input_tokens.toLocaleString()} input tokens`,
    `${tu.total_cache_read_tokens.toLocaleString()} cached`,
    cachePct,
    `$${tu.total_estimated_cost_usd.toFixed(4)} total spend`,
  ].filter(Boolean).join(' · ')

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-3">
        <MetricChip label="Total Memos" value={String(stats.total_memos)} sub={`${stats.memos_with_sources} with SEC citations`} />
        <MetricChip label="Grounding Rate" value={`${groundingPct}%`} sub="memos with SEC sources" />
        <MetricChip
          label="Avg Eval Score"
          value={avgScore !== '—' ? `${avgScore} / 5.0` : '—'}
          sub={tu.memos_tracked > 0 ? `over ${tu.memos_tracked} scored memos` : undefined}
        />
        <MetricChip
          label="Est. Total Cost"
          value={costStr}
          sub={tu.avg_cost_per_memo_usd != null ? `~$${tu.avg_cost_per_memo_usd.toFixed(4)} / memo` : undefined}
        />
      </div>

      {tu.memos_tracked > 0 && (
        <div className="bg-[#F6F3EE] border border-black/8 px-4 py-3">
          <p className="text-[11px] font-medium text-[#5C5C5C] uppercase tracking-widest mb-3">
            Avg Eval Scores — 5 Dimensions
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-5 gap-2">
            {EVAL_DIMS.map(({ key, label }) => (
              <div key={key} className="space-y-1">
                <p className="text-[11px] text-[#5C5C5C]">{label}</p>
                <ScoreMiniBar score={stats.avg_eval_scores[key] ?? null} />
              </div>
            ))}
          </div>
        </div>
      )}

      {tu.memos_tracked > 0 && (
        <p className="text-[11px] text-[#5C5C5C]/60 px-1">{tokenRow}</p>
      )}
    </div>
  )
}

export default function DashboardPage() {
  const router = useRouter()
  const [memos, setMemos] = useState<Memo[]>([])
  const [user, setUser] = useState<UserProfile | null>(null)
  const [loading, setLoading] = useState(true)
  const [showModal, setShowModal] = useState(false)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [stats, setStats] = useState<MemoStats | null>(null)
  const [statsLoading, setStatsLoading] = useState(false)
  const [metricsOpen, setMetricsOpen] = useState(false)

  const loadData = useCallback(async () => {
    try {
      const [memosData, userData] = await Promise.all([getMemos(), getMe()])
      const sorted = [...memosData].sort(
        (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
      )
      setMemos(sorted)
      setUser(userData)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to load data'
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

  const loadStats = useCallback(async () => {
    setStatsLoading(true)
    try {
      const data = await getMemoStats()
      setStats(data)
    } catch {
      // non-fatal
    } finally {
      setStatsLoading(false)
    }
  }, [])

  useEffect(() => {
    const token = typeof window !== 'undefined' ? localStorage.getItem('alphalens_token') : null
    if (!token) { router.replace('/auth/login'); return }
    loadData()
    loadStats()
  }, [router, loadData, loadStats])

  function handleLogout() {
    clearToken()
    router.replace('/auth/login')
  }

  async function handleDelete(e: React.MouseEvent, id: string) {
    e.stopPropagation()
    if (!confirm('Delete this memo?')) return
    setDeletingId(id)
    try {
      await deleteMemo(id)
      setMemos((prev) => prev.filter((m) => m.id !== id))
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to delete memo')
    } finally {
      setDeletingId(null)
    }
  }

  function handleModalClose() {
    setShowModal(false)
    loadData()
    loadStats()
  }

  const showMetrics = !loading && memos.length > 0

  return (
    <div className="min-h-screen">
      {/* Nav */}
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
                <Link href="/dashboard" className="text-[12px] font-medium text-[#2E2A47] border-b border-[#2E2A47] pb-0.5">
                  Memos
                </Link>
                <Link href="/portfolio" className="text-[12px] text-[#5C5C5C] hover:text-[#121212] transition-colors">
                  Portfolio
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
              {user && (
                <span className="hidden lg:block text-[12px] text-[#5C5C5C]">{user.email}</span>
              )}
              <button onClick={handleLogout} className="text-[12px] text-[#5C5C5C] hover:text-[#121212] transition-colors">
                Sign out
              </button>
            </div>
          </div>
        </div>
      </nav>

      <div className="max-w-[1000px] mx-auto px-6 py-8">
        {/* Page header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="font-serif text-[28px] font-normal text-[#121212] leading-tight">Investment Memos</h1>
            <p className="text-[13px] text-[#5C5C5C] mt-1">
              {memos.length > 0
                ? `${memos.length} memo${memos.length !== 1 ? 's' : ''} generated`
                : 'AI-generated investment analysis'}
            </p>
          </div>
          <button
            onClick={() => setShowModal(true)}
            className="flex items-center gap-2 px-4 py-2 bg-[#2E2A47] hover:bg-[#1E1A35] text-white text-[13px] font-medium transition-colors"
          >
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            Generate Memo
          </button>
        </div>

        {/* System Metrics */}
        {showMetrics && (
          <div className="mb-8 bg-white border border-black/8 overflow-hidden">
            <button
              onClick={() => setMetricsOpen((o) => !o)}
              className="w-full flex items-center justify-between px-4 py-3 hover:bg-black/[0.02] transition-colors"
              aria-expanded={metricsOpen}
            >
              <div className="flex items-center gap-2">
                <svg className="w-3.5 h-3.5 text-[#2E2A47]" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                </svg>
                <span className="text-[13px] font-medium text-[#121212]">System Metrics</span>
                {stats && (
                  <span className="text-[12px] text-[#5C5C5C]">
                    · {stats.total_memos} memo{stats.total_memos !== 1 ? 's' : ''}
                    {stats.token_usage.total_estimated_cost_usd != null &&
                      ` · $${stats.token_usage.total_estimated_cost_usd.toFixed(4)} est. spend`}
                  </span>
                )}
              </div>
              <svg
                className={`w-3.5 h-3.5 text-[#5C5C5C] transition-transform duration-200 ${metricsOpen ? 'rotate-180' : ''}`}
                fill="none" viewBox="0 0 24 24" stroke="currentColor"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
              </svg>
            </button>

            <div className={`transition-all duration-200 overflow-hidden ${metricsOpen ? 'max-h-[9999px] opacity-100' : 'max-h-0 opacity-0'}`}>
              <div className="border-t border-black/8 px-4 py-4">
                {statsLoading ? (
                  <div className="space-y-3 animate-pulse">
                    <div className="flex gap-3">
                      {[...Array(4)].map((_, i) => (
                        <div key={i} className="flex-1 h-16 bg-black/5" />
                      ))}
                    </div>
                    <div className="h-10 bg-black/5" />
                    <div className="h-4 bg-black/5 w-2/3" />
                  </div>
                ) : stats ? (
                  <SystemMetricsPanel stats={stats} />
                ) : (
                  <p className="text-[13px] text-[#5C5C5C] py-2">Could not load system metrics.</p>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="mb-6 px-4 py-3 bg-[#A14A44]/8 border border-[#A14A44]/20 text-[#A14A44] text-[13px] flex items-center justify-between">
            <span>{error}</span>
            <button onClick={() => setError(null)} className="ml-4 text-[#A14A44]/60 hover:text-[#A14A44]">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        )}

        {/* Content */}
        {loading ? (
          <div className="flex flex-col items-center justify-center py-32 gap-3">
            <span className="w-5 h-5 border-2 border-[#2E2A47] border-t-transparent rounded-full animate-spin" />
            <p className="text-[13px] text-[#5C5C5C]">Loading memos...</p>
          </div>
        ) : memos.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-32 text-center">
            <div className="w-12 h-12 bg-white border border-black/8 flex items-center justify-center mb-5">
              <svg className="w-6 h-6 text-[#5C5C5C]/40" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                  d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
            </div>
            <h3 className="font-serif text-[18px] text-[#121212] mb-2">No memos yet</h3>
            <p className="text-[13px] text-[#5C5C5C] mb-6 max-w-xs">
              Generate your first investment memo. Pick a strategy and sector.
            </p>
            <button
              onClick={() => setShowModal(true)}
              className="px-5 py-2 bg-[#2E2A47] hover:bg-[#1E1A35] text-white text-[13px] font-medium transition-colors"
            >
              Generate your first memo
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {memos.map((memo) => (
              <div key={memo.id} className="relative group">
                <MemoCard memo={memo} />
                <button
                  onClick={(e) => handleDelete(e, memo.id)}
                  disabled={deletingId === memo.id}
                  className="absolute top-3 right-3 w-7 h-7 flex items-center justify-center bg-white border border-black/8 text-[#5C5C5C] hover:text-[#A14A44] hover:border-[#A14A44]/30 opacity-0 group-hover:opacity-100 transition-all duration-150 disabled:cursor-not-allowed"
                  aria-label="Delete memo"
                >
                  {deletingId === memo.id ? (
                    <span className="w-3 h-3 border border-[#5C5C5C] border-t-transparent rounded-full animate-spin" />
                  ) : (
                    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                        d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                  )}
                </button>
              </div>
            ))}
          </div>
        )}

        <p className="mt-12 text-center text-[11px] text-[#5C5C5C]/50">
          For educational use only. Not financial advice.
        </p>
      </div>

      {showModal && <GenerateMemoModal onClose={handleModalClose} />}
    </div>
  )
}
