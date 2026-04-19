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
  'Information Technology',
  'Health Care',
  'Financials',
  'Consumer Discretionary',
  'Communication Services',
  'Industrials',
  'Consumer Staples',
  'Energy',
  'Utilities',
  'Real Estate',
  'Materials',
] as const
type Sector = (typeof SECTORS)[number]

type GenerationPhase = 'idle' | 'screening' | 'fetching' | 'writing' | 'done' | 'error'

const phaseMessages: Record<GenerationPhase, string> = {
  idle: '',
  screening: 'Screening stocks...',
  fetching: 'Fetching market data...',
  writing: 'Writing investment memo...',
  done: 'Memo generated!',
  error: 'Generation failed.',
}

export default function GenerateMemoModal({ onClose }: GenerateMemoModalProps) {
  const router = useRouter()
  const [selectedStrategy, setSelectedStrategy] = useState<Strategy | null>(null)
  const [selectedSector, setSelectedSector] = useState<Sector | null>(null)
  const [phase, setPhase] = useState<GenerationPhase>('idle')
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const eventSourceRef = useRef<EventSource | null>(null)

  // Close on Escape key
  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.key === 'Escape' && phase === 'idle') onClose()
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [onClose, phase])

  // Clean up EventSource on unmount
  useEffect(() => {
    return () => {
      eventSourceRef.current?.close()
    }
  }, [])

  const isGenerating = phase !== 'idle' && phase !== 'error'

  function handleGenerate() {
    if (!selectedStrategy || !selectedSector || isGenerating) return

    setPhase('screening')
    setErrorMessage(null)

    const es = streamMemoGeneration(selectedStrategy.toLowerCase(), selectedSector)
    eventSourceRef.current = es

    let dotTimer: ReturnType<typeof setTimeout> | null = null

    function advancePhase() {
      // Cycle through phases to give visual feedback
      setPhase((current) => {
        if (current === 'screening') return 'fetching'
        if (current === 'fetching') return 'writing'
        return current
      })
      dotTimer = setTimeout(advancePhase, 4000)
    }

    dotTimer = setTimeout(advancePhase, 3000)

    es.addEventListener('message', (e: MessageEvent<string>) => {
      try {
        const parsed = JSON.parse(e.data) as { type: string; memo_id?: string; phase?: string }
        if (parsed.type === 'done' && parsed.memo_id) {
          if (dotTimer) clearTimeout(dotTimer)
          es.close()
          setPhase('done')
          router.push(`/memo/${parsed.memo_id}`)
          onClose()
        } else if (parsed.type === 'phase' && parsed.phase) {
          const phaseMap: Record<string, GenerationPhase> = {
            screening: 'screening',
            fetching: 'fetching',
            writing: 'writing',
          }
          if (phaseMap[parsed.phase]) {
            if (dotTimer) clearTimeout(dotTimer)
            setPhase(phaseMap[parsed.phase])
          }
        } else if (parsed.type === 'error') {
          if (dotTimer) clearTimeout(dotTimer)
          es.close()
          setPhase('error')
          setErrorMessage('Generation failed on the server. Please try again.')
        }
      } catch {
        // ignore malformed events
      }
    })

    es.addEventListener('error', () => {
      if (dotTimer) clearTimeout(dotTimer)
      es.close()
      setPhase('error')
      setErrorMessage('Connection error during generation. Please try again.')
    })
  }

  const strategyButtonClass = (s: Strategy) =>
    `px-4 py-2.5 rounded-lg text-sm font-medium border transition-all ${
      selectedStrategy === s
        ? 'bg-indigo-600 border-indigo-500 text-white'
        : 'bg-gray-800 border-gray-700 text-gray-300 hover:border-gray-500 hover:text-white'
    } ${isGenerating ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}`

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/70 backdrop-blur-sm"
        onClick={() => { if (phase === 'idle') onClose() }}
      />

      {/* Modal */}
      <div className="relative z-10 w-full max-w-md bg-gray-900 border border-gray-800 rounded-2xl shadow-2xl shadow-black/60">
        {/* Header */}
        <div className="flex items-center justify-between px-6 pt-6 pb-4 border-b border-gray-800">
          <h2 className="text-lg font-semibold text-white">Generate Investment Memo</h2>
          {phase === 'idle' && (
            <button
              onClick={onClose}
              className="text-gray-500 hover:text-gray-300 transition-colors"
              aria-label="Close modal"
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          )}
        </div>

        <div className="px-6 py-5 space-y-6">
          {/* Strategy selector */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-3">Strategy</label>
            <div className="grid grid-cols-2 gap-2">
              {STRATEGIES.map((s) => (
                <button
                  key={s}
                  disabled={isGenerating}
                  onClick={() => !isGenerating && setSelectedStrategy(s)}
                  className={strategyButtonClass(s)}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>

          {/* Sector selector */}
          <div>
            <label htmlFor="sector" className="block text-sm font-medium text-gray-300 mb-2">
              Sector
            </label>
            <select
              id="sector"
              disabled={isGenerating}
              value={selectedSector ?? ''}
              onChange={(e) => setSelectedSector(e.target.value as Sector || null)}
              className="w-full px-3.5 py-2.5 bg-gray-800 border border-gray-700 rounded-lg text-gray-100 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <option value="" disabled>Select a sector...</option>
              {SECTORS.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </div>

          {/* Generation progress */}
          {phase !== 'idle' && (
            <div className={`px-4 py-3 rounded-lg border ${
              phase === 'error'
                ? 'bg-red-900/30 border-red-700'
                : 'bg-indigo-900/20 border-indigo-800'
            }`}>
              <div className="flex items-center gap-3">
                {phase !== 'error' && phase !== 'done' && (
                  <span className="w-4 h-4 border-2 border-indigo-400 border-t-transparent rounded-full animate-spin shrink-0" />
                )}
                {phase === 'done' && (
                  <svg className="w-4 h-4 text-green-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                )}
                {phase === 'error' && (
                  <svg className="w-4 h-4 text-red-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                )}
                <p className={`text-sm font-medium ${phase === 'error' ? 'text-red-300' : 'text-indigo-300'}`}>
                  {errorMessage ?? phaseMessages[phase]}
                </p>
              </div>

              {/* Progress steps */}
              {phase !== 'error' && (
                <div className="mt-3 flex gap-1.5">
                  {(['screening', 'fetching', 'writing'] as const).map((p) => {
                    const steps: GenerationPhase[] = ['screening', 'fetching', 'writing', 'done']
                    const currentIdx = steps.indexOf(phase)
                    const stepIdx = steps.indexOf(p)
                    const isActive = stepIdx === currentIdx
                    const isDone = stepIdx < currentIdx

                    return (
                      <div
                        key={p}
                        className={`h-1.5 flex-1 rounded-full transition-all duration-500 ${
                          isDone
                            ? 'bg-indigo-400'
                            : isActive
                            ? 'bg-indigo-500 animate-pulse'
                            : 'bg-gray-700'
                        }`}
                      />
                    )
                  })}
                </div>
              )}
            </div>
          )}

          {/* Error retry */}
          {phase === 'error' && (
            <button
              onClick={() => setPhase('idle')}
              className="w-full py-2 text-sm text-gray-400 hover:text-gray-200 transition-colors"
            >
              Reset and try again
            </button>
          )}
        </div>

        {/* Footer */}
        {(phase === 'idle' || phase === 'error') && (
          <div className="px-6 pb-6">
            <button
              onClick={handleGenerate}
              disabled={!selectedStrategy || !selectedSector || isGenerating}
              className="w-full py-2.5 px-4 bg-indigo-600 hover:bg-indigo-500 disabled:bg-gray-800 disabled:text-gray-600 disabled:cursor-not-allowed rounded-lg text-white font-medium text-sm transition-colors"
            >
              Generate Memo
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
