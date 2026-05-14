'use client'

import { useState, useEffect } from 'react'
import { useRouter, useParams } from 'next/navigation'
import Link from 'next/link'
import { getMemo, clearToken, type Memo } from '@/lib/api'

import MemoDetail from '@/components/MemoDetail'
import ChatPanel from '@/components/ChatPanel'
import ThinkingTrace from '@/components/ThinkingTrace'
import SourcesPanel from '@/components/SourcesPanel'
import EvalScoreBar from '@/components/EvalScoreBar'

export default function MemoPage() {
  const router = useRouter()
  const params = useParams<{ id: string }>()
  const memoId = params.id

  const [memo, setMemo] = useState<Memo | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const token = typeof window !== 'undefined' ? localStorage.getItem('alphalens_token') : null
    if (!token) { router.replace('/auth/login'); return }

    async function load() {
      try {
        const data = await getMemo(memoId)
        setMemo(data)
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : 'Failed to load memo'
        if (msg.includes('401') || msg.includes('Unauthorized')) {
          clearToken()
          router.replace('/auth/login')
        } else {
          setError(msg)
        }
      } finally {
        setLoading(false)
      }
    }

    load()
  }, [memoId, router])

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <span className="w-5 h-5 border-2 border-[#2E2A47] border-t-transparent rounded-full animate-spin" />
          <p className="text-[#5C5C5C] text-[13px]">Loading memo...</p>
        </div>
      </div>
    )
  }

  if (error || !memo) {
    return (
      <div className="min-h-screen flex items-center justify-center px-4">
        <div className="text-center">
          <div className="w-12 h-12 bg-[#A14A44]/8 border border-[#A14A44]/20 flex items-center justify-center mx-auto mb-4">
            <svg className="w-6 h-6 text-[#A14A44]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <h2 className="font-serif text-[18px] text-[#121212] mb-1">
            {error ?? 'Memo not found'}
          </h2>
          <p className="text-[#5C5C5C] text-[13px] mb-5">
            The memo could not be loaded. It may have been deleted.
          </p>
          <Link
            href="/dashboard"
            className="px-4 py-2 bg-[#2E2A47] hover:bg-[#1E1A35] text-white text-[13px] font-medium transition-colors"
          >
            Back to dashboard
          </Link>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen flex flex-col">
      {/* Nav */}
      <nav className="sticky top-0 z-10 bg-white border-b border-black/8">
        <div className="max-w-[1000px] mx-auto px-6">
          <div className="flex items-center justify-between h-12">
            <div className="flex items-center gap-2">
              <Link
                href="/dashboard"
                className="flex items-center gap-1.5 text-[12px] text-[#5C5C5C] hover:text-[#121212] transition-colors"
              >
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                </svg>
                Dashboard
              </Link>
              <span className="text-[#5C5C5C]/40">/</span>
              <span className="text-[13px] text-[#121212] font-medium">{memo.ticker}</span>
            </div>

            <div className="flex items-center gap-2">
              <div className="w-6 h-6 bg-[#2E2A47] flex items-center justify-center">
                <span className="text-white text-[9px] font-bold tracking-wider">AL</span>
              </div>
              <span className="text-[13px] font-medium text-[#121212] tracking-tight">AlphaLens</span>
            </div>
          </div>
        </div>
      </nav>

      {/* Main content */}
      <div className="flex-1 max-w-[1000px] w-full mx-auto px-6 py-6">
        <div className="flex flex-col lg:flex-row gap-5 h-full">
          {/* Left: memo (60%) */}
          <div className="lg:w-[60%] flex-shrink-0">
            <div className="bg-white border border-black/8 p-6 lg:sticky lg:top-16 lg:max-h-[calc(100vh-5rem)] lg:overflow-y-auto">
              <MemoDetail memo={memo} />

              {(memo.eval_scores !== null ||
                (memo.thinking_trace?.length ?? 0) > 0 ||
                (memo.sources?.length ?? 0) > 0) && (
                <div className="border-t border-black/8 mt-6 pt-6 flex flex-col gap-5">
                  {memo.eval_scores !== null && (
                    <EvalScoreBar scores={memo.eval_scores} />
                  )}
                  {(memo.thinking_trace?.length ?? 0) > 0 && (
                    <ThinkingTrace thinkingBlocks={memo.thinking_trace!} />
                  )}
                  {(memo.sources?.length ?? 0) > 0 && (
                    <SourcesPanel sources={memo.sources!} />
                  )}
                </div>
              )}
            </div>
          </div>

          {/* Right: chat (40%) */}
          <div className="lg:w-[40%] lg:sticky lg:top-16 lg:h-[calc(100vh-5rem)]">
            <ChatPanel memoId={memoId} />
          </div>
        </div>
      </div>
    </div>
  )
}
