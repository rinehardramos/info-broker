/**
 * BurnChart — 30-day rolling burn display + month-end projection.
 *
 * Hand-rolled SVG bar chart — no new chart library introduced.
 * Recharts/chart.js were not present in package.json.
 */
import type { WalletForecast } from '@/api/v3'

interface Props {
  forecast: WalletForecast
}

const BAR_W = 8
const BAR_GAP = 2
const CHART_H = 80

export function BurnChart({ forecast }: Props) {
  const { last_30d_consumed, last_7d_consumed, rolling_daily_avg, month_end_projection, days_until_floor_ru } = forecast

  // Build 4-week approximate bars (week buckets from 30d data)
  // We only have 30d total and 7d recent — split into 4 buckets:
  // weeks 1-3 = (30d - 7d) / 3 each, week 4 = 7d
  const week4 = last_7d_consumed
  const week123 = last_30d_consumed - last_7d_consumed
  const weekAvg = Math.max(0, week123 / 3)
  const bars = [
    Math.round(weekAvg),
    Math.round(weekAvg),
    Math.round(weekAvg),
    Math.round(week4),
  ]
  const maxBar = Math.max(...bars, 1)

  const svgW = bars.length * (BAR_W + BAR_GAP) - BAR_GAP

  return (
    <div
      style={{
        background: 'var(--panel)',
        border: '1px solid var(--border)',
        borderRadius: 12,
        padding: '20px 24px',
        flex: 1,
        minWidth: 220,
      }}
    >
      <div style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 12 }}>30-day burn</div>

      {/* SVG bar chart */}
      <svg width={svgW} height={CHART_H} style={{ overflow: 'visible' }}>
        {bars.map((v, i) => {
          const barH = Math.max(2, (v / maxBar) * (CHART_H - 16))
          const x = i * (BAR_W + BAR_GAP)
          const y = CHART_H - barH - 16
          const isLatest = i === bars.length - 1
          return (
            <g key={i}>
              <rect
                x={x}
                y={y}
                width={BAR_W}
                height={barH}
                rx={2}
                fill={isLatest ? '#a78bfa' : 'rgba(167,139,250,0.35)'}
              />
              <text
                x={x + BAR_W / 2}
                y={CHART_H - 4}
                textAnchor="middle"
                fontSize={8}
                fill="var(--muted)"
              >
                {`W${i + 1}`}
              </text>
            </g>
          )
        })}
      </svg>

      <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 5 }}>
        <StatLine label="Avg/day" value={`${rolling_daily_avg.toFixed(1)} RU`} />
        <StatLine label="Month-end est." value={`${month_end_projection.toLocaleString()} RU`} />
        {days_until_floor_ru !== null && days_until_floor_ru !== undefined ? (
          <StatLine
            label="Floor in"
            value={`${days_until_floor_ru}d`}
            warn={days_until_floor_ru < 7}
          />
        ) : (
          <StatLine label="Floor breach" value="Not projected" dimmed />
        )}
      </div>
    </div>
  )
}

function StatLine({
  label,
  value,
  warn,
  dimmed,
}: {
  label: string
  value: string
  warn?: boolean
  dimmed?: boolean
}) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12 }}>
      <span style={{ color: 'var(--muted)' }}>{label}</span>
      <span
        style={{
          color: warn ? '#f87171' : dimmed ? 'var(--subtext)' : 'var(--text)',
          fontVariantNumeric: 'tabular-nums',
        }}
      >
        {value}
      </span>
    </div>
  )
}
