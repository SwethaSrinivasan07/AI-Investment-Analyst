'use client'

import { useState, useEffect, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import {
  getSettings,
  updatePreferences,
  createSchedule,
  updateSchedule,
  deleteSchedule,
  clearToken,
  type UserSettings,
  type Schedule,
} from '@/lib/api'

const STRATEGIES = ['momentum', 'value', 'growth', 'dividend'] as const
const SECTORS = [
  'Technology', 'Healthcare', 'Financials', 'Consumer Discretionary',
  'Consumer Staples', 'Industrials', 'Energy', 'Materials',
  'Real Estate', 'Utilities', 'Communication Services',
] as const
const FREQUENCIES = [
  { value: 'daily', label: 'Daily' },
  { value: 'every2days', label: 'Every 2 days' },
  { value: 'weekly', label: 'Weekly' },
] as const

const MAX_SCHEDULES = 3

function capitalize(s: string) { return s.charAt(0).toUpperCase() + s.slice(1) }

function formatNextRun(dateStr: string | null): string {
  if (!dateStr) return '—'
  return new Date(dateStr).toLocaleDateString('en-US', {
    month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit', timeZoneName: 'short',
  })
}

function formatMemberSince(dateStr: string | undefined): string {
  if (!dateStr) return '—'
  return new Date(dateStr).toLocaleDateString('en-US', { month: 'long', year: 'numeric' })
}

function SkeletonBlock({ className }: { className?: string }) {
  return <div className={`bg-black/5 animate-pulse ${className ?? ''}`} />
}

function SettingsSkeleton() {
  return (
    <div className="space-y-6">
      {[0, 1, 2].map((i) => (
        <div key={i} className="bg-white border border-black/8 p-5 space-y-4">
          <SkeletonBlock className="h-3 w-24" />
          <SkeletonBlock className="h-9 w-full" />
          <SkeletonBlock className="h-9 w-full" />
          <SkeletonBlock className="h-9 w-32" />
        </div>
      ))}
    </div>
  )
}

function Toggle({ checked, onChange, disabled }: { checked: boolean; onChange: () => void; disabled?: boolean }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={onChange}
      disabled={disabled}
      className={`relative w-9 h-5 transition-colors focus:outline-none focus:ring-1 focus:ring-[#2E2A47] focus:ring-offset-1 disabled:cursor-not-allowed ${
        checked ? 'bg-[#2E2A47]' : 'bg-black/20'
      }`}
    >
      <span
        className={`absolute top-0.5 h-4 w-4 bg-white transition-transform ${
          checked ? 'translate-x-[18px]' : 'translate-x-0.5'
        }`}
      />
    </button>
  )
}

export default function SettingsPage() {
  const router = useRouter()

  const [settings, setSettings] = useState<UserSettings | null>(null)
  const [memberSince, setMemberSince] = useState<string | undefined>(undefined)
  const [pageLoading, setPageLoading] = useState(true)
  const [pageError, setPageError] = useState<string | null>(null)

  const [prefStrategy, setPrefStrategy] = useState('momentum')
  const [prefSector, setPrefSector] = useState('Technology')
  const [prefEmailNotifications, setPrefEmailNotifications] = useState(true)
  const [prefSaving, setPrefSaving] = useState(false)
  const [prefSuccess, setPrefSuccess] = useState(false)
  const [prefError, setPrefError] = useState<string | null>(null)

  const [showAddForm, setShowAddForm] = useState(false)
  const [newStrategy, setNewStrategy] = useState<string>('momentum')
  const [newSector, setNewSector] = useState<string>('Technology')
  const [newFrequency, setNewFrequency] = useState<string>('weekly')
  const [scheduleAdding, setScheduleAdding] = useState(false)
  const [scheduleError, setScheduleError] = useState<string | null>(null)
  const [busySchedules, setBusySchedules] = useState<Record<string, boolean>>({})

  const loadSettings = useCallback(async () => {
    try {
      const data = await getSettings()
      setSettings(data)
      const prefs = data.preferences
      if (typeof prefs.default_strategy === 'string') setPrefStrategy(prefs.default_strategy)
      if (typeof prefs.default_sector === 'string') setPrefSector(prefs.default_sector)
      if (typeof prefs.email_notifications === 'boolean') setPrefEmailNotifications(prefs.email_notifications)
      const raw = typeof window !== 'undefined' ? localStorage.getItem('alphalens_user') : null
      if (raw) { try { const u = JSON.parse(raw); setMemberSince(u.created_at) } catch { /* ignore */ } }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to load settings'
      if (msg.includes('401') || msg.includes('Unauthorized')) { clearToken(); router.replace('/auth/login') }
      else setPageError(msg)
    } finally {
      setPageLoading(false)
    }
  }, [router])

  useEffect(() => {
    const token = typeof window !== 'undefined' ? localStorage.getItem('alphalens_token') : null
    if (!token) { router.replace('/auth/login'); return }
    loadSettings()
  }, [router, loadSettings])

  async function handleSavePreferences(e: React.FormEvent) {
    e.preventDefault()
    setPrefSaving(true); setPrefError(null); setPrefSuccess(false)
    try {
      const updated = await updatePreferences({ default_strategy: prefStrategy, default_sector: prefSector, email_notifications: prefEmailNotifications })
      setSettings(updated); setPrefSuccess(true)
      setTimeout(() => setPrefSuccess(false), 3000)
    } catch (err: unknown) {
      setPrefError(err instanceof Error ? err.message : 'Failed to save preferences')
    } finally {
      setPrefSaving(false)
    }
  }

  async function handleAddSchedule(e: React.FormEvent) {
    e.preventDefault()
    setScheduleAdding(true); setScheduleError(null)
    try {
      const schedule = await createSchedule(newStrategy, newSector, newFrequency)
      setSettings((prev) => prev ? { ...prev, schedules: [...prev.schedules, schedule] } : prev)
      setShowAddForm(false); setNewStrategy('momentum'); setNewSector('Technology'); setNewFrequency('weekly')
    } catch (err: unknown) {
      setScheduleError(err instanceof Error ? err.message : 'Failed to create schedule')
    } finally {
      setScheduleAdding(false)
    }
  }

  async function handleToggleSchedule(schedule: Schedule) {
    setBusySchedules((prev) => ({ ...prev, [schedule.id]: true }))
    try {
      const updated = await updateSchedule(schedule.id, { enabled: !schedule.enabled })
      setSettings((prev) => prev ? { ...prev, schedules: prev.schedules.map((s) => s.id === updated.id ? updated : s) } : prev)
    } catch { /* non-critical */ } finally {
      setBusySchedules((prev) => ({ ...prev, [schedule.id]: false }))
    }
  }

  async function handleDeleteSchedule(id: string) {
    if (!confirm('Delete this schedule?')) return
    setBusySchedules((prev) => ({ ...prev, [id]: true }))
    try {
      await deleteSchedule(id)
      setSettings((prev) => prev ? { ...prev, schedules: prev.schedules.filter((s) => s.id !== id) } : prev)
    } catch { /* non-critical */ } finally {
      setBusySchedules((prev) => ({ ...prev, [id]: false }))
    }
  }

  const activeScheduleCount = settings?.schedules.filter((s) => s.enabled).length ?? 0

  return (
    <div className="min-h-screen">
      <nav className="sticky top-0 z-10 bg-white border-b border-black/8">
        <div className="max-w-[640px] mx-auto px-6">
          <div className="flex items-center justify-between h-12">
            <Link
              href="/dashboard"
              className="flex items-center gap-1.5 text-[12px] text-[#5C5C5C] hover:text-[#121212] transition-colors"
            >
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
              </svg>
              Dashboard
            </Link>
            <div className="flex items-center gap-2">
              <div className="w-6 h-6 bg-[#2E2A47] flex items-center justify-center">
                <span className="text-white text-[9px] font-bold tracking-wider">AL</span>
              </div>
              <span className="text-[13px] font-medium text-[#121212] tracking-tight">AlphaLens</span>
            </div>
          </div>
        </div>
      </nav>

      <div className="max-w-[640px] mx-auto px-6 py-8">
        <h1 className="font-serif text-[28px] font-normal text-[#121212] leading-tight mb-1">Settings</h1>
        <p className="text-[13px] text-[#5C5C5C] mb-8">Account, preferences, and memo schedules.</p>

        {pageError && (
          <div className="mb-5 px-4 py-3 bg-[#A14A44]/8 border border-[#A14A44]/20 text-[#A14A44] text-[13px] flex items-center justify-between">
            <span>{pageError}</span>
            <button onClick={() => setPageError(null)} className="ml-4 text-[#A14A44]/60 hover:text-[#A14A44]">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        )}

        {pageLoading ? <SettingsSkeleton /> : (
          <div className="space-y-6">

            {/* Account */}
            <section>
              <p className="text-[11px] font-medium text-[#5C5C5C] uppercase tracking-widest mb-3">Account</p>
              <div className="bg-white border border-black/8 p-5 space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-[13px] text-[#5C5C5C]">Email</span>
                  <span className="text-[13px] text-[#121212] font-medium">{settings?.email}</span>
                </div>
                <div className="border-t border-black/8" />
                <div className="flex items-center justify-between">
                  <span className="text-[13px] text-[#5C5C5C]">Member since</span>
                  <span className="text-[13px] text-[#121212]">{formatMemberSince(memberSince)}</span>
                </div>
              </div>
            </section>

            {/* Default Preferences */}
            <section>
              <p className="text-[11px] font-medium text-[#5C5C5C] uppercase tracking-widest mb-3">Default Preferences</p>
              <div className="bg-white border border-black/8 p-5">
                <form onSubmit={handleSavePreferences} className="space-y-4">
                  <div>
                    <label className="block text-[13px] text-[#5C5C5C] mb-2">Default strategy</label>
                    <div className="flex gap-1 bg-[#F6F3EE] border border-black/8 p-1">
                      {STRATEGIES.map((s) => (
                        <button
                          key={s} type="button" onClick={() => setPrefStrategy(s)}
                          className={`flex-1 py-1.5 text-[13px] font-medium transition-colors ${
                            prefStrategy === s ? 'bg-[#2E2A47] text-white' : 'text-[#5C5C5C] hover:text-[#121212]'
                          }`}
                        >
                          {capitalize(s)}
                        </button>
                      ))}
                    </div>
                  </div>

                  <div>
                    <label htmlFor="pref-sector" className="block text-[13px] text-[#5C5C5C] mb-2">Default sector</label>
                    <select
                      id="pref-sector"
                      value={prefSector}
                      onChange={(e) => setPrefSector(e.target.value)}
                      className="w-full bg-white border border-black/8 px-3 py-2 text-[#121212] text-[13px] focus:outline-none focus:ring-1 focus:ring-[#2E2A47]"
                    >
                      {SECTORS.map((sec) => <option key={sec} value={sec}>{sec}</option>)}
                    </select>
                  </div>

                  <div className="flex items-center justify-between py-1">
                    <div>
                      <p className="text-[13px] text-[#121212]">Email notifications</p>
                      <p className="text-[11px] text-[#5C5C5C] mt-0.5">Receive scheduled memos via email</p>
                    </div>
                    <Toggle checked={prefEmailNotifications} onChange={() => setPrefEmailNotifications((v) => !v)} />
                  </div>

                  {prefError && <p className="text-[13px] text-[#A14A44]">{prefError}</p>}
                  {prefSuccess && <p className="text-[13px] text-[#2F6B4F]">Preferences saved.</p>}

                  <div className="pt-1">
                    <button
                      type="submit"
                      disabled={prefSaving}
                      className="flex items-center gap-2 px-4 py-2 bg-[#2E2A47] hover:bg-[#1E1A35] disabled:opacity-50 disabled:cursor-not-allowed text-white text-[13px] font-medium transition-colors"
                    >
                      {prefSaving && <span className="w-3.5 h-3.5 border-2 border-white/40 border-t-white rounded-full animate-spin" />}
                      Save Preferences
                    </button>
                  </div>
                </form>
              </div>
            </section>

            {/* Memo Schedule */}
            <section>
              <div className="flex items-center justify-between mb-3">
                <p className="text-[11px] font-medium text-[#5C5C5C] uppercase tracking-widest">Memo Schedule</p>
                <span className="text-[11px] text-[#5C5C5C]">Max {MAX_SCHEDULES} active</span>
              </div>

              <div className="space-y-2">
                {settings?.schedules.length === 0 && !showAddForm && (
                  <div className="bg-white border border-black/8 px-5 py-7 text-center">
                    <p className="text-[13px] text-[#5C5C5C]">No schedules yet.</p>
                    <p className="text-[11px] text-[#5C5C5C]/60 mt-0.5">Add one below to receive automated memos.</p>
                  </div>
                )}

                {settings?.schedules.map((schedule) => (
                  <ScheduleCard
                    key={schedule.id}
                    schedule={schedule}
                    busy={!!busySchedules[schedule.id]}
                    onToggle={() => handleToggleSchedule(schedule)}
                    onDelete={() => handleDeleteSchedule(schedule.id)}
                  />
                ))}

                {scheduleError && (
                  <div className="px-4 py-3 bg-[#A14A44]/8 border border-[#A14A44]/20 text-[#A14A44] text-[13px] flex items-center justify-between">
                    <span>{scheduleError}</span>
                    <button onClick={() => setScheduleError(null)} className="ml-4 text-[#A14A44]/60 hover:text-[#A14A44]">
                      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                      </svg>
                    </button>
                  </div>
                )}

                {showAddForm ? (
                  <div className="bg-white border border-[#2E2A47]/20 p-5">
                    <p className="text-[13px] font-medium text-[#121212] mb-4">New schedule</p>
                    <form onSubmit={handleAddSchedule} className="space-y-3">
                      <div>
                        <label htmlFor="new-strategy" className="block text-[11px] text-[#5C5C5C] mb-1.5 uppercase tracking-wider">Strategy</label>
                        <select
                          id="new-strategy" value={newStrategy} onChange={(e) => setNewStrategy(e.target.value)}
                          className="w-full bg-white border border-black/8 px-3 py-2 text-[#121212] text-[13px] focus:outline-none focus:ring-1 focus:ring-[#2E2A47]"
                        >
                          {STRATEGIES.map((s) => <option key={s} value={s}>{capitalize(s)}</option>)}
                        </select>
                      </div>
                      <div>
                        <label htmlFor="new-sector" className="block text-[11px] text-[#5C5C5C] mb-1.5 uppercase tracking-wider">Sector</label>
                        <select
                          id="new-sector" value={newSector} onChange={(e) => setNewSector(e.target.value)}
                          className="w-full bg-white border border-black/8 px-3 py-2 text-[#121212] text-[13px] focus:outline-none focus:ring-1 focus:ring-[#2E2A47]"
                        >
                          {SECTORS.map((sec) => <option key={sec} value={sec}>{sec}</option>)}
                        </select>
                      </div>
                      <div>
                        <label className="block text-[11px] text-[#5C5C5C] mb-1.5 uppercase tracking-wider">Frequency</label>
                        <div className="flex gap-1 bg-[#F6F3EE] border border-black/8 p-1">
                          {FREQUENCIES.map(({ value, label }) => (
                            <button
                              key={value} type="button" onClick={() => setNewFrequency(value)}
                              className={`flex-1 py-1.5 text-[13px] font-medium transition-colors ${
                                newFrequency === value ? 'bg-[#2E2A47] text-white' : 'text-[#5C5C5C] hover:text-[#121212]'
                              }`}
                            >
                              {label}
                            </button>
                          ))}
                        </div>
                      </div>
                      <div className="flex gap-2 pt-1">
                        <button
                          type="submit" disabled={scheduleAdding}
                          className="flex items-center gap-2 px-4 py-2 bg-[#2E2A47] hover:bg-[#1E1A35] disabled:opacity-50 disabled:cursor-not-allowed text-white text-[13px] font-medium transition-colors"
                        >
                          {scheduleAdding && <span className="w-3.5 h-3.5 border-2 border-white/40 border-t-white rounded-full animate-spin" />}
                          Add
                        </button>
                        <button
                          type="button"
                          onClick={() => { setShowAddForm(false); setScheduleError(null) }}
                          className="px-4 py-2 text-[13px] text-[#5C5C5C] hover:text-[#121212] transition-colors"
                        >
                          Cancel
                        </button>
                      </div>
                    </form>
                  </div>
                ) : (
                  <button
                    onClick={() => {
                      if (activeScheduleCount >= MAX_SCHEDULES) {
                        setScheduleError(`Maximum of ${MAX_SCHEDULES} active schedules. Disable or delete one first.`)
                        return
                      }
                      setScheduleError(null); setShowAddForm(true)
                    }}
                    className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-white border border-dashed border-black/15 hover:border-[#2E2A47]/40 text-[13px] text-[#5C5C5C] hover:text-[#2E2A47] transition-colors"
                  >
                    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                    </svg>
                    Add Schedule
                  </button>
                )}

                <p className="text-[11px] text-[#5C5C5C]/50 pt-1">
                  Scheduled memos are generated automatically and emailed to you.
                </p>
              </div>
            </section>

          </div>
        )}

        <p className="mt-10 text-center text-[11px] text-[#5C5C5C]/50">
          For educational use only. Not financial advice.
        </p>
      </div>
    </div>
  )
}

interface ScheduleCardProps {
  schedule: Schedule
  busy: boolean
  onToggle: () => void
  onDelete: () => void
}

function ScheduleCard({ schedule, busy, onToggle, onDelete }: ScheduleCardProps) {
  const frequencyLabel = FREQUENCIES.find((f) => f.value === schedule.frequency)?.label ?? schedule.frequency
  return (
    <div className={`bg-white border px-4 py-3 flex items-center justify-between gap-4 transition-colors ${
      schedule.enabled ? 'border-black/8' : 'border-black/5 opacity-50'
    }`}>
      <div className="min-w-0">
        <p className="text-[13px] font-medium text-[#121212] truncate">
          {capitalize(schedule.strategy)} · {schedule.sector} · {frequencyLabel}
        </p>
        <p className="text-[11px] text-[#5C5C5C] mt-0.5">Next run: {formatNextRun(schedule.next_run_at)}</p>
      </div>
      <div className="flex items-center gap-3 shrink-0">
        <button
          type="button" role="switch" aria-checked={schedule.enabled} disabled={busy} onClick={onToggle}
          className={`relative w-9 h-5 transition-colors focus:outline-none disabled:cursor-not-allowed ${
            schedule.enabled ? 'bg-[#2E2A47]' : 'bg-black/20'
          }`}
        >
          <span className={`absolute top-0.5 h-4 w-4 bg-white transition-transform ${
            schedule.enabled ? 'translate-x-[18px]' : 'translate-x-0.5'
          }`} />
        </button>
        <button
          type="button" disabled={busy} onClick={onDelete}
          className="w-6 h-6 flex items-center justify-center text-[#5C5C5C]/40 hover:text-[#A14A44] transition-colors disabled:cursor-not-allowed"
          aria-label="Delete schedule"
        >
          {busy ? (
            <span className="w-3 h-3 border border-[#5C5C5C] border-t-transparent rounded-full animate-spin" />
          ) : (
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
            </svg>
          )}
        </button>
      </div>
    </div>
  )
}
