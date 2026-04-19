'use client'

import { useState, useEffect } from 'react'
import { useRouter, useParams } from 'next/navigation'
import Link from 'next/link'
import { getMemo, clearToken, type Memo } from '@/lib/api'
import MemoDetail from '@/components/MemoDetail'
import ChatPanel from '@/components/ChatPanel'

export default function MemoPage() {
  const router = useRouter()
  const params = useParams<{ id: string }>()
  const memoId = params.id

  const [memo, setMemo] = useState<Memo | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const token = typeof window !== 'undefined' ? localStorage.getItem('alphalens_token') : null
    if (!token) {
      router.replace('/auth/login')
      return
    }

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
      <div className="min-h-screen bg-gray-950 flex items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <span className="w-8 h-8 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
          <p className="text-gray-500 text-sm">Loading memo...</p>
        </div>
      </div>
    )
  }

  if (error || !memo) {
    return (
      <div className="min-h-screen bg-gray-950 flex items-center justify-center px-4">
        <div className="text-center">
          <div className="w-14 h-14 bg-red-900/30 border border-red-800 rounded-2xl flex items-center justify-center mx-auto mb-4">
            <svg className="w-7 h-7 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <h2 className="text-lg font-semibold text-gray-200 mb-2">
            {error ?? 'Memo not found'}
          </h2>
          <p className="text-gray-500 text-sm mb-6">
            The memo could not be loaded. It may have been deleted.
          </p>
          <Link
            href="/dashboard"
            className="px-5 py-2.5 bg-indigo-600 hover:bg-indigo-500 rounded-lg text-white text-sm font-medium transition-colors"
          >
            Back to dashboard
          </Link>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-950 flex flex-col">
      {/* Top nav */}
      <nav className="sticky top-0 z-10 bg-gray-950/80 backdrop-blur-md border-b border-gray-800">
        <div className="max-w-screen-2xl mx-auto px-4 sm:px-6">
          <div className="flex items-center justify-between h-14">
            <div className="flex items-center gap-3">
              {/* Back button */}
              <Link
                href="/dashboard"
                className="flex items-center gap-1.5 text-sm text-gray-400 hover:text-gray-200 transition-colors"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                </svg>
                Dashboard
              </Link>
              <span className="text-gray-700">/</span>
              <span className="text-sm text-gray-300 font-medium">{memo.ticker}</span>
            </div>

            <div className="flex items-center gap-2">
              <div className="w-6 h-6 bg-indigo-600 rounded-md flex items-center justify-center">
                <span className="text-white text-xs font-bold">A</span>
              </div>
              <span className="text-sm font-bold text-white">AlphaLens</span>
            </div>
          </div>
        </div>
      </nav>

      {/* Main content — two-column layout */}
      <div className="flex-1 max-w-screen-2xl w-full mx-auto px-4 sm:px-6 py-6">
        <div className="flex flex-col lg:flex-row gap-6 h-full">
          {/* Left: memo detail (60%) */}
          <div className="lg:w-[60%] flex-shrink-0">
            <div className="bg-gray-900 border border-gray-800 rounded-xl p-6 lg:sticky lg:top-20 lg:max-h-[calc(100vh-6rem)] lg:overflow-y-auto">
              <MemoDetail memo={memo} />
            </div>
          </div>

          {/* Right: chat panel (40%) */}
          <div className="lg:w-[40%] lg:sticky lg:top-20 lg:h-[calc(100vh-6rem)]">
            <ChatPanel memoId={memoId} />
          </div>
        </div>
      </div>
    </div>
  )
}
