'use client'

import { useState, useEffect } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { AreaChart, Area, ResponsiveContainer, Tooltip } from 'recharts'
import type { Memo } from '@/lib/api'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface MemoDetailProps {
  memo: Memo
}

interface PricePoint {
  date: string
  close: number
}

interface PriceData {
  data: PricePoint[]
  current_price: number
  price_change_1m_pct: number
  price_change_3m_pct: number
  rsi_14: number | null
}

// ── Helpers ───────────────────────────────────────────────────────────────────

const recommendationColors: Record<string, string> = {
  Buy:   'bg-[#2F6B4F]/8 text-[#2F6B4F] border border-[#2F6B4F]/20',
  Watch: 'bg-[#6B7280]/8 text-[#6B7280] border border-[#6B7280]/20',
  Pass:  'bg-[#A14A44]/8 text-[#A14A44] border border-[#A14A44]/20',
}

const convictionColors: Record<string, string> = {
  High:   'text-[#2F6B4F]',
  Medium: 'text-[#6B7280]',
  Low:    'text-[#A14A44]',
}

function formatDate(dateStr: string): string {
  try {
    return new Date(dateStr).toLocaleDateString('en-US', {
      weekday: 'short', month: 'short', day: 'numeric', year: 'numeric',
    })
  } catch { return dateStr }
}

function formatPrice(n: number): string {
  return n.toLocaleString('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 2 })
}

function formatChange(pct: number): string {
  return `${pct >= 0 ? '+' : ''}${pct.toFixed(2)}%`
}

function changeColor(pct: number): string {
  if (pct > 0) return 'text-[#2F6B4F]'
  if (pct < 0) return 'text-[#A14A44]'
  return 'text-[#5C5C5C]'
}

function rsiColor(rsi: number): string {
  if (rsi < 30) return 'text-[#2F6B4F]'
  if (rsi > 70) return 'text-[#A14A44]'
  return 'text-[#6B7280]'
}

// ── Skeletons ─────────────────────────────────────────────────────────────────

function ChartSkeleton() {
  return (
    <div className="w-full h-24 bg-black/[0.03] animate-pulse flex items-end px-4 pb-3 gap-0.5">
      {Array.from({ length: 30 }).map((_, i) => (
        <div key={i} className="flex-1 bg-black/[0.06]" style={{ height: `${30 + Math.sin(i * 0.5) * 20}%` }} />
      ))}
    </div>
  )
}

function MetricsSkeleton() {
  return (
    <div className="flex flex-wrap gap-2">
      {Array.from({ length: 5 }).map((_, i) => (
        <div key={i} className="h-14 w-32 bg-black/[0.04] animate-pulse" />
      ))}
    </div>
  )
}

// ── Metric pill ───────────────────────────────────────────────────────────────

function MetricPill({ label, value, valueClass = 'text-[#121212]', badge = false }: {
  label: string; value: string; valueClass?: string; badge?: boolean
}) {
  return (
    <div className={`flex flex-col gap-0.5 px-3 py-2.5 border border-black/8 min-w-[7rem] ${badge ? 'bg-[#2E2A47]/5' : 'bg-white'}`}>
      <span className="text-[10px] font-medium tracking-widest text-[#5C5C5C] uppercase">{label}</span>
      <span className={`text-[13px] font-medium leading-tight ${valueClass}`}>{value}</span>
    </div>
  )
}

// ── Chart tooltip ─────────────────────────────────────────────────────────────

function ChartTooltip({ active, payload, label }: { active?: boolean; payload?: Array<{ value: number }>; label?: string }) {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-white border border-black/8 px-3 py-2 text-[11px]">
      <p className="text-[#5C5C5C] mb-0.5">{label}</p>
      <p className="text-[#121212] font-medium">{formatPrice(payload[0].value)}</p>
    </div>
  )
}

// ── Markdown components ───────────────────────────────────────────────────────

const markdownComponents = {
  h1: ({ children }: { children?: React.ReactNode }) => (
    <h1 className="font-serif text-[24px] font-normal text-[#121212] mt-8 mb-4 pb-2 border-b border-black/8">
      {children}
    </h1>
  ),
  h2: ({ children }: { children?: React.ReactNode }) => (
    <h2 className="flex items-center gap-3 font-serif text-[18px] font-normal text-[#121212] mt-8 mb-3 pt-5 border-t border-black/8">
      <span className="inline-block w-0.5 h-5 bg-[#2E2A47] flex-shrink-0" />
      {children}
    </h2>
  ),
  h3: ({ children }: { children?: React.ReactNode }) => (
    <h3 className="text-[14px] font-medium text-[#121212] mt-5 mb-2">{children}</h3>
  ),
  p: ({ children }: { children?: React.ReactNode }) => (
    <p className="font-serif text-[15px] text-[#121212] leading-[1.75] mb-4">{children}</p>
  ),
  strong: ({ children }: { children?: React.ReactNode }) => (
    <strong className="text-[#121212] font-medium">{children}</strong>
  ),
  a: ({ href, children }: { href?: string; children?: React.ReactNode }) => (
    <a href={href} className="text-[#2E2A47] hover:underline transition-colors" target="_blank" rel="noopener noreferrer">
      {children}
    </a>
  ),
  code: ({ inline, children }: { inline?: boolean; children?: React.ReactNode }) =>
    inline ? (
      <code className="text-[#2E2A47] bg-black/5 px-1.5 py-0.5 text-[0.8em] font-mono">
        {children}
      </code>
    ) : (
      <code className="block text-[#5C5C5C] bg-[#F6F3EE] border border-black/8 p-4 text-[13px] font-mono overflow-x-auto mb-4">
        {children}
      </code>
    ),
  pre: ({ children }: { children?: React.ReactNode }) => (
    <pre className="bg-[#F6F3EE] border border-black/8 overflow-x-auto mb-4">{children}</pre>
  ),
  blockquote: ({ children }: { children?: React.ReactNode }) => (
    <blockquote className="my-5 pl-4 pr-4 py-3 border-l-2 border-[#2E2A47] bg-[#2E2A47]/[0.03]">
      <div className="font-serif text-[#5C5C5C] text-[14px] leading-relaxed [&>p]:mb-0">{children}</div>
    </blockquote>
  ),
  ul: ({ children }: { children?: React.ReactNode }) => (
    <ul className="my-4 space-y-1.5 pl-1">{children}</ul>
  ),
  ol: ({ children }: { children?: React.ReactNode }) => (
    <ol className="my-4 space-y-1.5 pl-5 list-decimal marker:text-[#5C5C5C]">{children}</ol>
  ),
  li: ({ children }: { children?: React.ReactNode }) => (
    <li className="flex items-start gap-2.5 font-serif text-[15px] text-[#121212] leading-relaxed">
      <span className="mt-[0.45rem] w-1 h-1 bg-[#2E2A47] flex-shrink-0" />
      <span>{children}</span>
    </li>
  ),
  table: ({ children }: { children?: React.ReactNode }) => (
    <div className="my-5 overflow-x-auto border border-black/8">
      <table className="w-full text-[13px]">{children}</table>
    </div>
  ),
  thead: ({ children }: { children?: React.ReactNode }) => (
    <thead className="bg-[#F6F3EE] border-b border-black/8">{children}</thead>
  ),
  tbody: ({ children }: { children?: React.ReactNode }) => (
    <tbody className="divide-y divide-black/[0.04]">{children}</tbody>
  ),
  th: ({ children }: { children?: React.ReactNode }) => (
    <th className="text-left text-[#5C5C5C] font-medium px-4 py-2.5 text-[11px] uppercase tracking-wider">
      {children}
    </th>
  ),
  td: ({ children }: { children?: React.ReactNode }) => (
    <td className="text-[#121212] px-4 py-2.5">{children}</td>
  ),
  hr: () => <hr className="my-6 border-black/8" />,
}

// ── Main component ────────────────────────────────────────────────────────────

export default function MemoDetail({ memo }: MemoDetailProps) {
  const [priceData, setPriceData] = useState<PriceData | null>(null)
  const [priceLoading, setPriceLoading] = useState(true)

  useEffect(() => {
    let cancelled = false

    async function fetchPrice() {
      setPriceLoading(true)
      try {
        const token = typeof window !== 'undefined' ? localStorage.getItem('alphalens_token') : null
        const headers: HeadersInit = token ? { Authorization: `Bearer ${token}` } : {}
        const res = await fetch(`${API_URL}/api/stocks/${memo.ticker}/price`, { headers })
        if (!res.ok) throw new Error('price fetch failed')
        const data = (await res.json()) as PriceData
        if (!cancelled) setPriceData(data)
      } catch {
        if (!cancelled) setPriceData(null)
      } finally {
        if (!cancelled) setPriceLoading(false)
      }
    }

    fetchPrice()
    return () => { cancelled = true }
  }, [memo.ticker])

  const recClass = recommendationColors[memo.recommendation] ?? 'bg-black/5 text-[#5C5C5C] border border-black/8'
  const convClass = convictionColors[memo.conviction] ?? 'text-[#5C5C5C]'

  return (
    <div className="flex flex-col h-full">

      {/* Header */}
      <div className="mb-6 pb-5 border-b border-black/8">
        <div className="flex flex-wrap items-start justify-between gap-4 mb-4">
          <div>
            <div className="flex items-center gap-3 mb-1">
              <h1 className="font-serif text-[28px] font-normal text-[#121212] leading-none">{memo.ticker}</h1>
              <span className={`text-[11px] font-medium px-2 py-0.5 ${recClass}`}>
                {memo.recommendation}
              </span>
            </div>
            <p className="text-[13px] text-[#5C5C5C]">{memo.company_name}</p>
          </div>

          <div className="flex flex-col items-end gap-1 text-[13px]">
            <div>
              <span className="text-[#5C5C5C]">Conviction: </span>
              <span className={`font-medium ${convClass}`}>{memo.conviction}</span>
            </div>
            {memo.data_as_of && (
              <div className="text-[11px] text-[#5C5C5C]/60">
                Data as of {formatDate(memo.data_as_of)}
              </div>
            )}
          </div>
        </div>

        <p className="text-[11px] text-[#5C5C5C]/50 italic">
          For educational use only. Not financial advice.
        </p>
      </div>

      {/* Price chart */}
      {priceLoading ? (
        <div className="mb-5"><ChartSkeleton /></div>
      ) : priceData && priceData.data?.length > 0 ? (
        <div className="mb-5 bg-[#F6F3EE] border border-black/8 overflow-hidden">
          <div className="px-4 pt-3 pb-1 text-[11px] text-[#5C5C5C] font-medium tracking-wide">
            {memo.ticker} — 3-Month Price
          </div>
          <ResponsiveContainer width="100%" height={100}>
            <AreaChart data={priceData.data} margin={{ top: 4, right: 0, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id="priceGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#2E2A47" stopOpacity={0.10} />
                  <stop offset="95%" stopColor="#2E2A47" stopOpacity={0} />
                </linearGradient>
              </defs>
              <Tooltip content={<ChartTooltip />} />
              <Area type="monotone" dataKey="close" stroke="#2E2A47" strokeWidth={1.5}
                fill="url(#priceGrad)" dot={false} activeDot={{ r: 2, fill: '#2E2A47', strokeWidth: 0 }} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      ) : null}

      {/* Key metrics */}
      {priceLoading ? (
        <div className="mb-6"><MetricsSkeleton /></div>
      ) : (
        <div className="mb-6 flex flex-wrap gap-2">
          {priceData && (
            <>
              <MetricPill label="Price" value={formatPrice(priceData.current_price)} />
              <MetricPill label="1M" value={formatChange(priceData.price_change_1m_pct)} valueClass={changeColor(priceData.price_change_1m_pct)} />
              <MetricPill label="3M" value={formatChange(priceData.price_change_3m_pct)} valueClass={changeColor(priceData.price_change_3m_pct)} />
              {priceData.rsi_14 != null && (
                <MetricPill label="RSI (14)" value={priceData.rsi_14.toFixed(1)} valueClass={rsiColor(priceData.rsi_14)} />
              )}
            </>
          )}
          <MetricPill
            label="Strategy"
            value={memo.strategy.charAt(0).toUpperCase() + memo.strategy.slice(1)}
            valueClass="text-[#2E2A47]"
            badge
          />
          <MetricPill label="Sector" value={memo.sector} valueClass="text-[#5C5C5C]" badge />
        </div>
      )}

      {/* Memo body */}
      <div className="flex-1 overflow-y-auto">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={markdownComponents as never}
        >
          {memo.markdown_text}
        </ReactMarkdown>
      </div>
    </div>
  )
}
