'use client'

import { useState, useEffect, useRef } from 'react'
import { useRouter } from 'next/navigation'
import { streamMemoGeneration } from '@/lib/api'

interface GenerateMemoModalProps {
  onClose: () => void
}

const STRATEGIES = ['Momentum', 'Value', 'Growth', 'Dividend'] as const
type Strategy = (typeof STRATEGIES)[number]

const SECTORS = [
  'Information Technology', 'Health Care', 'Financials', 'Consumer Discretionary',
  'Communication Services', 'Industrials', 'Consumer Staples', 'Energy',
  'Utilities', 'Real Estate', 'Materials',
] as const
type Sector = (typeof SECTORS)[number]

type GenerationPhase = 'idle' | 'screening' | 'fetching' | 'writing' | 'done' | 'error'
type PickMode = 'auto' | 'specific'

const phaseMessages: Record<GenerationPhase, string> = {
  idle: '',
  screening: 'Screening stocks...',
  fetching: 'Fetching market data...',
  writing: 'Writing investment memo...',
  done: 'Memo generated.',
  error: 'Generation failed.',
}

export default function GenerateMemoModal({ onClose }: GenerateMemoModalProps) {
  const router = useRouter()
  const [pickMode, setPickMode] = useState<PickMode>('auto')
  const [selectedStrategy, setSelectedStrategy] = useState<Strategy | null>(null)
  const [selectedSector, setSelectedSector] = useState<Sector | null>(null)
  const [tickerInput, setTickerInput] = useState('')
  const [phase, setPhase] = useState<GenerationPhase>('idle')
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const eventSourceRef = useRef<EventSource | null>(null)

  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.key === 'Escape' && phase === 'idle') onClose()
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [onClose, phase])

  useEffect(() => {
    return () => { eventSourceRef.current?.close() }
  }, [])

  const isGenerating = phase !== 'idle' && phase !== 'error'

  const canGenerate = !isGenerating && selectedStrategy !== null && (
    pickMode === 'auto' ? selectedSector !== null : tickerInput.trim().length >= 1
  )

  function handleGenerate() {
    if (!canGenerate || !selectedStrategy) return

    setPhase('screening')
    setErrorMessage(null)

    const strategy = selectedStrategy.toLowerCase()
    const sector = pickMode === 'auto' ? (selectedSector as string) : 'Auto'
    const ticker = pickMode === 'specific' ? tickerInput.trim().toUpperCase() : undefined

    const es = streamMemoGeneration(strategy, sector, ticker)
    eventSourceRef.current = es

    es.onmessage = (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data as string) as {
          type: string
          message?: string
          content?: string
          memo_id?: string
          ticker?: string
          recommendation?: string
          conviction?: string
        }

        if (data.type === 'status') {
          const msg = (data.message ?? '').toLowerCase()
          if (msg.includes('screen')) setPhase('screening')
          else if (msg.includes('fetch') || msg.includes('research') || msg.includes('bull') || msg.includes('bear') || msg.includes('peer')) setPhase('fetching')
          else if (msg.includes('writ') || msg.includes('memo')) setPhase('writing')
        } else if (data.type === 'token') {
          setPhase('writing')
        } else if (data.type === 'done') {
          es.close()
          setPhase('done')
          if (data.memo_id) {
            router.push(`/memo/${data.memo_id}`)
            onClose()
          }
        } else if (data.type === 'error') {
          es.close()
          setPhase('error')
          setErrorMessage(data.message ?? 'Generation failed. Please try again.')
        }
      } catch {
        // malformed SSE line — ignore
      }
    }

    es.onerror = () => {
      es.close()
      setPhase('error')
      setErrorMessage('Connection error during generation. Please try again.')
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div
        className="absolute inset-0 bg-black/30"
        onClick={() => { if (phase === 'idle') onClose() }}
      />

      <div className="relative z-10 w-full max-w-[420px] bg-white border border-black/8">
        {/* Header */}
        <div className="flex items-center justify-between px-5 pt-5 pb-4 border-b border-black/8">
          <h2 className="text-[15px] font-medium text-[#121212]">Generate Memo</h2>
          {phase === 'idle' && (
            <button
              onClick={onClose}
              className="text-[#5C5C5C]/60 hover:text-[#121212] transition-colors"
              aria-label="Close"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          )}
        </div>

        <div className="px-5 py-5 space-y-5">
          {/* Mode toggle */}
          <div>
            <label className="block text-[11px] font-medium text-[#5C5C5C] uppercase tracking-widest mb-2">Mode</label>
            <div className="flex bg-[#F6F3EE] border border-black/8 p-1 gap-1">
              {(['auto', 'specific'] as const).map((mode) => (
                <button
                  key={mode}
                  disabled={isGenerating}
                  onClick={() => !isGenerating && setPickMode(mode)}
                  className={`flex-1 py-1.5 px-3 text-[13px] font-medium transition-colors ${
                    pickMode === mode ? 'bg-[#2E2A47] text-white' : 'text-[#5C5C5C] hover:text-[#121212]'
                  } ${isGenerating ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}`}
                >
                  {mode === 'auto' ? 'Auto-pick' : 'Specific stock'}
                </button>
              ))}
            </div>
          </div>

          {/* Strategy */}
          <div>
            <label className="block text-[11px] font-medium text-[#5C5C5C] uppercase tracking-widest mb-2">Strategy</label>
            <div className="grid grid-cols-2 gap-1.5">
              {STRATEGIES.map((s) => (
                <button
                  key={s}
                  disabled={isGenerating}
                  onClick={() => !isGenerating && setSelectedStrategy(s)}
                  className={`px-4 py-2 text-[13px] font-medium border transition-colors ${
                    selectedStrategy === s
                      ? 'bg-[#2E2A47] border-[#2E2A47] text-white'
                      : 'bg-white border-black/8 text-[#5C5C5C] hover:border-black/20 hover:text-[#121212]'
                  } ${isGenerating ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}`}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>

          {/* Sector */}
          {pickMode === 'auto' && (
            <div>
              <label htmlFor="sector" className="block text-[11px] font-medium text-[#5C5C5C] uppercase tracking-widest mb-2">
                Sector
              </label>
              <select
                id="sector"
                disabled={isGenerating}
                value={selectedSector ?? ''}
                onChange={(e) => setSelectedSector(e.target.value as Sector || null)}
                className="w-full px-3 py-2 bg-white border border-black/8 text-[#121212] text-[13px] focus:outline-none focus:ring-1 focus:ring-[#2E2A47] disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <option value="" disabled>Select a sector...</option>
                {SECTORS.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>
          )}

          {/* Ticker */}
          {pickMode === 'specific' && (
            <div>
              <label htmlFor="ticker" className="block text-[11px] font-medium text-[#5C5C5C] uppercase tracking-widest mb-2">
                Ticker Symbol
              </label>
              <input
                id="ticker"
                type="text"
                disabled={isGenerating}
                value={tickerInput}
                onChange={(e) => setTickerInput(e.target.value.toUpperCase().slice(0, 6))}
                placeholder="e.g. NVDA, TSLA, AAPL"
                className="w-full px-3 py-2 bg-white border border-black/8 text-[#121212] text-[13px] placeholder-[#5C5C5C]/40 focus:outline-none focus:ring-1 focus:ring-[#2E2A47] disabled:opacity-50 disabled:cursor-not-allowed tracking-widest uppercase"
              />
              <p className="mt-1.5 text-[11px] text-[#5C5C5C]/60">
                Sector detected automatically from market data.
              </p>
            </div>
          )}

          {/* Progress */}
          {phase !== 'idle' && (
            <div className={`px-4 py-3 border ${
              phase === 'error'
                ? 'bg-[#A14A44]/8 border-[#A14A44]/20'
                : 'bg-[#2E2A47]/5 border-[#2E2A47]/15'
            }`}>
              <div className="flex items-center gap-3">
                {phase !== 'error' && phase !== 'done' && (
                  <span className="w-3.5 h-3.5 border-2 border-[#2E2A47] border-t-transparent rounded-full animate-spin shrink-0" />
                )}
                {phase === 'done' && (
                  <svg className="w-3.5 h-3.5 text-[#2F6B4F] shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                )}
                {phase === 'error' && (
                  <svg className="w-3.5 h-3.5 text-[#A14A44] shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                )}
                <p className={`text-[13px] font-medium ${phase === 'error' ? 'text-[#A14A44]' : 'text-[#2E2A47]'}`}>
                  {errorMessage ?? phaseMessages[phase]}
                </p>
              </div>

              {phase !== 'error' && (
                <div className="mt-3 flex gap-1">
                  {(['screening', 'fetching', 'writing'] as const).map((p) => {
                    const steps: GenerationPhase[] = ['screening', 'fetching', 'writing', 'done']
                    const currentIdx = steps.indexOf(phase)
                    const stepIdx = steps.indexOf(p)
                    const isActive = stepIdx === currentIdx
                    const isDone = stepIdx < currentIdx

                    return (
                      <div
                        key={p}
                        className={`h-0.5 flex-1 transition-all duration-500 ${
                          isDone ? 'bg-[#2E2A47]' : isActive ? 'bg-[#2E2A47] animate-pulse' : 'bg-black/10'
                        }`}
                      />
                    )
                  })}
                </div>
              )}
            </div>
          )}

          {phase === 'error' && (
            <button
              onClick={() => setPhase('idle')}
              className="w-full py-2 text-[13px] text-[#5C5C5C] hover:text-[#121212] transition-colors"
            >
              Reset and try again
            </button>
          )}
        </div>

        {/* Footer */}
        {(phase === 'idle' || phase === 'error') && (
          <div className="px-5 pb-5">
            <button
              onClick={handleGenerate}
              disabled={!canGenerate}
              className="w-full py-2.5 px-4 bg-[#2E2A47] hover:bg-[#1E1A35] disabled:bg-black/5 disabled:text-[#5C5C5C]/40 disabled:cursor-not-allowed text-white font-medium text-[13px] transition-colors"
            >
              Generate Memo
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
