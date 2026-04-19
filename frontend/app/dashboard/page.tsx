'use client'

import { useState, useEffect, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import { getMemos, getMe, clearToken, deleteMemo, type Memo, type UserProfile } from '@/lib/api'
import MemoCard from '@/components/MemoCard'
import GenerateMemoModal from '@/components/GenerateMemoModal'

export default function DashboardPage() {
  const router = useRouter()
  const [memos, setMemos] = useState<Memo[]>([])
  const [user, setUser] = useState<UserProfile | null>(null)
  const [loading, setLoading] = useState(true)
  const [showModal, setShowModal] = useState(false)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const loadData = useCallback(async () => {
    try {
      const [memosData, userData] = await Promise.all([getMemos(), getMe()])
      // Sort newest first
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

  useEffect(() => {
    const token = typeof window !== 'undefined' ? localStorage.getItem('alphalens_token') : null
    if (!token) {
      router.replace('/auth/login')
      return
    }
    loadData()
  }, [router, loadData])

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
    // Reload memos in case one was just generated
    loadData()
  }

  return (
    <div className="min-h-screen bg-gray-950">
      {/* Top nav */}
      <nav className="sticky top-0 z-10 bg-gray-950/80 backdrop-blur-md border-b border-gray-800">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-14">
            {/* Brand */}
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 bg-indigo-600 rounded-md flex items-center justify-center">
                <span className="text-white text-xs font-bold">A</span>
              </div>
              <span className="text-lg font-bold text-white tracking-tight">AlphaLens</span>
            </div>

            {/* Right side */}
            <div className="flex items-center gap-4">
              {user && (
                <span className="hidden sm:block text-sm text-gray-400">{user.email}</span>
              )}
              <button
                onClick={handleLogout}
                className="text-sm text-gray-400 hover:text-gray-200 transition-colors"
              >
                Sign out
              </button>
            </div>
          </div>
        </div>
      </nav>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Page header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-2xl font-bold text-white">Investment Memos</h1>
            <p className="text-sm text-gray-500 mt-1">
              {memos.length > 0
                ? `${memos.length} memo${memos.length !== 1 ? 's' : ''} generated`
                : 'AI-generated investment analysis'}
            </p>
          </div>
          <button
            onClick={() => setShowModal(true)}
            className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 rounded-lg text-white text-sm font-medium transition-colors"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            Generate Memo
          </button>
        </div>

        {/* Error banner */}
        {error && (
          <div className="mb-6 px-4 py-3 bg-red-900/40 border border-red-700 rounded-lg text-red-300 text-sm flex items-center justify-between">
            <span>{error}</span>
            <button onClick={() => setError(null)} className="text-red-400 hover:text-red-200 ml-4">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        )}

        {/* Content */}
        {loading ? (
          <div className="flex flex-col items-center justify-center py-32 gap-4">
            <span className="w-8 h-8 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
            <p className="text-gray-500 text-sm">Loading memos...</p>
          </div>
        ) : memos.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-32 text-center">
            <div className="w-16 h-16 bg-gray-900 border border-gray-800 rounded-2xl flex items-center justify-center mb-4">
              <svg className="w-8 h-8 text-gray-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                  d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
            </div>
            <h3 className="text-lg font-semibold text-gray-300 mb-2">No memos yet</h3>
            <p className="text-gray-500 text-sm mb-6 max-w-xs">
              Generate your first investment memo to get started. Pick a strategy and sector.
            </p>
            <button
              onClick={() => setShowModal(true)}
              className="px-5 py-2.5 bg-indigo-600 hover:bg-indigo-500 rounded-lg text-white text-sm font-medium transition-colors"
            >
              Generate your first memo
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {memos.map((memo) => (
              <div key={memo.id} className="relative group">
                <MemoCard memo={memo} />
                {/* Delete button — appears on hover */}
                <button
                  onClick={(e) => handleDelete(e, memo.id)}
                  disabled={deletingId === memo.id}
                  className="absolute top-3 right-3 w-7 h-7 flex items-center justify-center rounded-lg bg-gray-800/80 text-gray-500 hover:text-red-400 hover:bg-red-900/40 opacity-0 group-hover:opacity-100 transition-all duration-150 disabled:cursor-not-allowed"
                  aria-label="Delete memo"
                >
                  {deletingId === memo.id ? (
                    <span className="w-3 h-3 border border-gray-500 border-t-transparent rounded-full animate-spin" />
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

        <p className="mt-12 text-center text-xs text-gray-700">
          For educational use only. Not financial advice.
        </p>
      </div>

      {showModal && <GenerateMemoModal onClose={handleModalClose} />}
    </div>
  )
}
