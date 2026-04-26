'use client'

import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  CartesianGrid,
  ReferenceLine,
} from 'recharts'

export interface BacktestChartDataPoint {
  date: string
  portfolio: number
  spy: number
  sector_etf: number
}

interface BacktestChartProps {
  data: BacktestChartDataPoint[]
  strategyLabel: string
  sectorLabel: string
}

interface TooltipPayload {
  name: string
  value: number
  color: string
}

interface CustomTooltipProps {
  active?: boolean
  label?: string
  payload?: TooltipPayload[]
}

function CustomTooltip({ active, label, payload }: CustomTooltipProps) {
  if (!active || !payload || payload.length === 0) return null

  return (
    <div className="bg-white border border-black/8 px-3 py-2.5 text-[12px]">
      <p className="text-[#5C5C5C] mb-1.5 text-[11px] font-medium">{label}</p>
      {payload.map((entry) => (
        <div key={entry.name} className="flex items-center gap-2 mb-1">
          <span
            className="inline-block w-2 h-px flex-shrink-0"
            style={{ borderTop: `2px solid ${entry.color}` }}
          />
          <span className="text-[#5C5C5C] w-28 truncate text-[11px]">{entry.name}</span>
          <span
            className={`font-medium tabular-nums text-[12px] ${
              entry.value >= 100 ? 'text-[#2F6B4F]' : 'text-[#A14A44]'
            }`}
          >
            {entry.value.toFixed(1)}
          </span>
        </div>
      ))}
    </div>
  )
}

function formatXAxis(dateStr: string, index: number, total: number): string {
  const step = Math.max(1, Math.floor(total / 6))
  if (index % step !== 0) return ''
  const d = new Date(dateStr)
  return d.toLocaleDateString('en-US', { month: 'short', year: '2-digit' })
}

export default function BacktestChart({
  data,
  strategyLabel,
  sectorLabel,
}: BacktestChartProps) {
  if (!data || data.length === 0) {
    return (
      <div className="flex items-center justify-center h-64 text-[#5C5C5C] text-[13px]">
        No chart data available.
      </div>
    )
  }

  const total = data.length

  return (
    <ResponsiveContainer width="100%" height={300}>
      <LineChart
        data={data}
        margin={{ top: 8, right: 16, left: 0, bottom: 8 }}
      >
        <CartesianGrid strokeDasharray="4 2" stroke="rgba(0,0,0,0.06)" vertical={false} />
        <ReferenceLine y={100} stroke="rgba(0,0,0,0.12)" strokeDasharray="4 2" />

        <XAxis
          dataKey="date"
          tick={{ fill: '#5C5C5C', fontSize: 11 }}
          tickLine={false}
          axisLine={{ stroke: 'rgba(0,0,0,0.08)' }}
          tickFormatter={(val, idx) => formatXAxis(val as string, idx, total)}
        />
        <YAxis
          tick={{ fill: '#5C5C5C', fontSize: 11 }}
          tickLine={false}
          axisLine={false}
          tickFormatter={(v) => `${(v as number).toFixed(0)}`}
          width={38}
          domain={['auto', 'auto']}
        />

        <Tooltip content={<CustomTooltip />} />

        <Legend
          wrapperStyle={{ paddingTop: '12px', fontSize: '11px' }}
          formatter={(value) => (
            <span style={{ color: '#5C5C5C' }}>{value}</span>
          )}
        />

        <Line
          type="monotone"
          dataKey="portfolio"
          name={`${strategyLabel} / ${sectorLabel}`}
          stroke="#2E2A47"
          strokeWidth={1.5}
          dot={false}
          activeDot={{ r: 3, fill: '#2E2A47', strokeWidth: 0 }}
        />
        <Line
          type="monotone"
          dataKey="spy"
          name="SPY (S&P 500)"
          stroke="#2F6B4F"
          strokeWidth={1.5}
          dot={false}
          activeDot={{ r: 3, fill: '#2F6B4F', strokeWidth: 0 }}
        />
        <Line
          type="monotone"
          dataKey="sector_etf"
          name={`${sectorLabel} ETF`}
          stroke="#A14A44"
          strokeWidth={1.5}
          dot={false}
          activeDot={{ r: 3, fill: '#A14A44', strokeWidth: 0 }}
        />
      </LineChart>
    </ResponsiveContainer>
  )
}
