'use client'

import { useState } from 'react'
import { PortfolioAlert, markAlertRead, markAllAlertsRead, triggerMonitorRun } from '@/lib/api'

interface Props {
  alerts: PortfolioAlert[]
  onAlertsChange: (alerts: PortfolioAlert[]) => void
}

const severityStyles: Record<string, { bar: string; badge: string; label: string }> = {
  action:  { bar: 'bg-red-500',    badge: 'bg-red-50 text-red-700 border-red-200',    label: 'Action' },
  warning: { bar: 'bg-amber-400',  badge: 'bg-amber-50 text-amber-700 border-amber-200', label: 'Watch' },
  info:    { bar: 'bg-[#2E2A47]',  badge: 'bg-indigo-50 text-[#2E2A47] border-indigo-200', label: 'Info' },
}

export default function AlertsPanel({ alerts, onAlertsChange }: Props) {
  const [running, setRunning] = useState(false)
  const [runMsg, setRunMsg] = useState<string | null>(null)

  const unread = alerts.filter(a => !a.read).length

  async function handleMarkRead(id: string) {
    await markAlertRead(id).catch(() => null)
    onAlertsChange(alerts.map(a => a.id === id ? { ...a, read: true } : a))
  }

  async function handleMarkAll() {
    await markAllAlertsRead().catch(() => null)
    onAlertsChange(alerts.map(a => ({ ...a, read: true })))
  }

  async function handleRunMonitor() {
    setRunning(true)
    setRunMsg(null)
    try {
      const res = await triggerMonitorRun()
      setRunMsg(res.detail)
    } catch {
      setRunMsg('Monitor triggered — check back in a moment.')
    } finally {
      setRunning(false)
    }
  }

  if (alerts.length === 0) {
    return (
      <div className="border border-black/8 p-6 text-center">
        <p className="text-sm text-gray-500 mb-3">No alerts yet.</p>
        <button
          onClick={handleRunMonitor}
          disabled={running}
          className="text-xs px-3 py-1.5 border border-black/8 hover:bg-black/4 transition-colors disabled:opacity-50"
        >
          {running ? 'Running…' : 'Run monitor now'}
        </button>
        {runMsg && <p className="text-xs text-gray-500 mt-2">{runMsg}</p>}
      </div>
    )
  }

  return (
    <div className="border border-black/8">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-3 border-b border-black/8">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-[#2E2A47]">Alerts</span>
          {unread > 0 && (
            <span className="text-xs bg-red-500 text-white rounded-full px-1.5 py-0.5 leading-none">
              {unread}
            </span>
          )}
        </div>
        <div className="flex items-center gap-3">
          {unread > 0 && (
            <button
              onClick={handleMarkAll}
              className="text-xs text-gray-500 hover:text-[#2E2A47] transition-colors"
            >
              Mark all read
            </button>
          )}
          <button
            onClick={handleRunMonitor}
            disabled={running}
            className="text-xs px-3 py-1 border border-black/8 hover:bg-black/4 transition-colors disabled:opacity-50"
          >
            {running ? 'Running…' : 'Refresh'}
          </button>
        </div>
      </div>

      {runMsg && (
        <div className="px-5 py-2 text-xs text-gray-500 border-b border-black/8 bg-gray-50">
          {runMsg}
        </div>
      )}

      {/* Alert rows */}
      <ul className="divide-y divide-black/8">
        {alerts.map(alert => {
          const s = severityStyles[alert.severity] ?? severityStyles.info
          return (
            <li
              key={alert.id}
              className={`flex gap-3 px-5 py-4 transition-colors ${alert.read ? 'opacity-60' : 'bg-white'}`}
            >
              {/* Severity bar */}
              <div className={`w-0.5 flex-shrink-0 ${s.bar} rounded-full`} />

              <div className="flex-1 min-w-0">
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-0.5">
                      {alert.ticker && (
                        <span className="text-xs font-mono font-semibold text-[#2E2A47]">
                          {alert.ticker}
                        </span>
                      )}
                      <span className={`text-[10px] px-1.5 py-0.5 border rounded-sm ${s.badge}`}>
                        {s.label}
                      </span>
                      {!alert.read && (
                        <span className="w-1.5 h-1.5 bg-red-500 rounded-full flex-shrink-0" />
                      )}
                    </div>
                    <p className="text-xs font-medium text-gray-900 leading-snug">{alert.title}</p>
                    <p className="text-xs text-gray-500 mt-0.5 leading-relaxed">{alert.message}</p>
                  </div>

                  {!alert.read && (
                    <button
                      onClick={() => handleMarkRead(alert.id)}
                      className="flex-shrink-0 text-[10px] text-gray-400 hover:text-gray-700 transition-colors mt-0.5"
                      title="Mark as read"
                    >
                      ✕
                    </button>
                  )}
                </div>

                <p className="text-[10px] text-gray-400 mt-1.5">
                  {new Date(alert.created_at).toLocaleString(undefined, {
                    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
                  })}
                </p>
              </div>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
