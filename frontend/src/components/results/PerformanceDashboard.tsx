import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  getPerformanceDashboard,
  TechniquePerf,
  TacticPerf,
  getMetricsSummary,
  getRunHistory,
  MetricsSummary,
  RunHistoryItem,
} from '../../api/v3'

const SOURCE_COLORS: Record<string, string> = {
  A: '#22c55e', B: '#4ade80', C: '#facc15', D: '#fb923c', E: '#f87171', F: '#6b7280',
}

const STATUS_COLORS: Record<string, string> = {
  succeeded: '#4ade80',
  failed: '#f87171',
  running: '#60a5fa',
  awaiting_input: '#fbbf24',
  budget_exhausted: '#fb923c',
}

function parseGrade(g: string): [string, string] {
  if (g.length === 2 && 'ABCDEF'.includes(g[0]) && '123456'.includes(g[1])) return [g[0], g[1]]
  if (g.length === 1 && 'ABCDEF'.includes(g[0])) return [g[0], '?']
  return ['F', '6']
}

function GradePill({ grade }: { grade: string }) {
  const [src, cred] = parseGrade(grade)
  const color = SOURCE_COLORS[src] ?? '#6b7280'
  return (
    <span
      style={{
        background: color + '22',
        border: `1px solid ${color}`,
        color,
        borderRadius: 4,
        padding: '1px 7px',
        fontSize: 11,
        fontWeight: 700,
        minWidth: 28,
        display: 'inline-block',
        textAlign: 'center',
        letterSpacing: '0.05em',
      }}
      title={`Admiralty: ${src}${cred}`}
    >
      {src}{cred}
    </span>
  )
}

function StatusBadge({ status }: { status: string }) {
  const color = STATUS_COLORS[status] ?? '#6b7280'
  return (
    <span
      style={{
        background: color + '22',
        border: `1px solid ${color}`,
        color,
        borderRadius: 4,
        padding: '1px 7px',
        fontSize: 11,
        fontWeight: 600,
        whiteSpace: 'nowrap',
      }}
    >
      {status}
    </span>
  )
}

function StatCard({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <div
      style={{
        background: 'var(--panel)',
        border: '1px solid var(--border)',
        borderRadius: 6,
        padding: '10px 14px',
        minWidth: 120,
        flex: '1 1 120px',
      }}
    >
      <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: 18, fontWeight: 700, color: 'var(--accent)' }}>{value}</div>
      {sub && <div style={{ fontSize: 10, color: 'var(--muted)', marginTop: 2 }}>{sub}</div>}
    </div>
  )
}

type SortKey<T> = keyof T

function useSortableTable<T>(initialKey: SortKey<T>, initialDir: 'asc' | 'desc') {
  const [sortKey, setSortKey] = useState<SortKey<T>>(initialKey)
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>(initialDir)

  function toggle(key: SortKey<T>) {
    if (key === sortKey) {
      setSortDir(d => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortKey(key)
      setSortDir('desc')
    }
  }

  function sort(rows: T[]): T[] {
    return [...rows].sort((a, b) => {
      const av = a[sortKey]
      const bv = b[sortKey]
      if (typeof av === 'number' && typeof bv === 'number') {
        return sortDir === 'asc' ? av - bv : bv - av
      }
      const as = String(av)
      const bs = String(bv)
      return sortDir === 'asc' ? as.localeCompare(bs) : bs.localeCompare(as)
    })
  }

  function header(label: string, key: SortKey<T>) {
    const active = key === sortKey
    return (
      <th
        key={String(key)}
        onClick={() => toggle(key)}
        style={{
          cursor: 'pointer',
          userSelect: 'none',
          padding: '6px 10px',
          textAlign: 'left',
          fontSize: 11,
          color: active ? 'var(--accent)' : 'var(--muted)',
          borderBottom: '1px solid var(--border)',
          whiteSpace: 'nowrap',
        }}
      >
        {label}
        {active && (
          <span style={{ marginLeft: 4 }}>{sortDir === 'asc' ? '▲' : '▼'}</span>
        )}
      </th>
    )
  }

  return { sort, header, sortKey, sortDir }
}

function TechniqueTable({ rows }: { rows: TechniquePerf[] }) {
  const { sort, header } = useSortableTable<TechniquePerf>('avg_numeric', 'desc')
  const sorted = sort(rows)

  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
        <thead>
          <tr>
            {header('Tool', 'tool')}
            {header('Avg Grade', 'avg_grade')}
            {header('Score', 'avg_numeric')}
            {header('Runs', 'runs')}
            {header('Results', 'total_results')}
            {header('Errors', 'errors')}
            {header('Error Rate', 'error_rate')}
          </tr>
        </thead>
        <tbody>
          {sorted.map((t, i) => (
            <tr
              key={t.tool}
              style={{
                background: i % 2 === 0 ? 'var(--panel)' : 'var(--panel2)',
              }}
            >
              <td style={{ padding: '5px 10px', fontFamily: 'monospace', color: 'var(--text)' }}>
                {t.tool}
              </td>
              <td style={{ padding: '5px 10px' }}>
                <GradePill grade={t.avg_grade} />
              </td>
              <td style={{ padding: '5px 10px', color: 'var(--subtext)' }}>{t.avg_numeric}</td>
              <td style={{ padding: '5px 10px', color: 'var(--subtext)' }}>{t.runs}</td>
              <td style={{ padding: '5px 10px', color: 'var(--subtext)' }}>{t.total_results}</td>
              <td style={{ padding: '5px 10px', color: t.errors > 0 ? '#f87171' : 'var(--muted)' }}>
                {t.errors}
              </td>
              <td style={{ padding: '5px 10px', color: t.error_rate > 0.3 ? '#f87171' : 'var(--muted)' }}>
                {(t.error_rate * 100).toFixed(0)}%
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function TacticTable({ rows }: { rows: TacticPerf[] }) {
  const { sort, header } = useSortableTable<TacticPerf>('avg_numeric', 'desc')
  const sorted = sort(rows)

  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
        <thead>
          <tr>
            {header('Tactic', 'name')}
            {header('Avg Grade', 'avg_grade')}
            {header('Score', 'avg_numeric')}
            {header('Runs', 'runs')}
            {header('Avg Yield', 'avg_yield')}
          </tr>
        </thead>
        <tbody>
          {sorted.map((t, i) => (
            <tr
              key={t.name}
              style={{
                background: i % 2 === 0 ? 'var(--panel)' : 'var(--panel2)',
              }}
            >
              <td style={{ padding: '5px 10px', color: 'var(--text)' }}>{t.name}</td>
              <td style={{ padding: '5px 10px' }}>
                <GradePill grade={t.avg_grade} />
              </td>
              <td style={{ padding: '5px 10px', color: 'var(--subtext)' }}>{t.avg_numeric}</td>
              <td style={{ padding: '5px 10px', color: 'var(--subtext)' }}>{t.runs}</td>
              <td style={{ padding: '5px 10px', color: 'var(--subtext)' }}>
                {(t.avg_yield * 100).toFixed(1)}%
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// --- Metrics sections ---

const sectionHeadStyle: React.CSSProperties = {
  fontSize: 12,
  fontWeight: 600,
  color: 'var(--accent)',
  marginBottom: 10,
  textTransform: 'uppercase',
  letterSpacing: '0.05em',
}

const thStyle: React.CSSProperties = {
  padding: '5px 10px',
  textAlign: 'left',
  fontSize: 11,
  color: 'var(--muted)',
  borderBottom: '1px solid var(--border)',
  whiteSpace: 'nowrap',
}

function MetricsSummarySection({ data }: { data: MetricsSummary }) {
  return (
    <section style={{ marginBottom: 28 }}>
      <h2 style={sectionHeadStyle}>Run Summary — last {data.period_days} days</h2>

      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginBottom: 10 }}>
        <StatCard label="Total Runs" value={data.runs.total} />
        <StatCard
          label="Success Rate"
          value={`${(data.runs.success_rate * 100).toFixed(1)}%`}
          sub={`${data.runs.succeeded} succeeded`}
        />
        <StatCard label="Failed" value={data.runs.failed} />
        <StatCard label="Budget Exhausted" value={data.runs.budget_exhausted} />
      </div>

      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginBottom: 16 }}>
        <StatCard label="Avg Latency" value={`${data.latency.avg_seconds.toFixed(1)}s`} />
        <StatCard label="P50 Latency" value={`${data.latency.p50_seconds.toFixed(1)}s`} />
        <StatCard label="P95 Latency" value={`${data.latency.p95_seconds.toFixed(1)}s`} />
      </div>

      {data.steps.length > 0 && (
        <div style={{ marginBottom: 16 }}>
          <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
            Top Nodes
          </div>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
              <thead>
                <tr>
                  <th style={thStyle}>Node Type</th>
                  <th style={thStyle}>Total Calls</th>
                  <th style={thStyle}>Success Rate</th>
                  <th style={thStyle}>Avg Items</th>
                </tr>
              </thead>
              <tbody>
                {data.steps.map((s, i) => {
                  const rate = s.total > 0 ? (s.succeeded / s.total) * 100 : 0
                  return (
                    <tr key={s.node_type} style={{ background: i % 2 === 0 ? 'var(--panel)' : 'var(--panel2)' }}>
                      <td style={{ padding: '5px 10px', fontFamily: 'monospace', color: 'var(--text)' }}>{s.node_type}</td>
                      <td style={{ padding: '5px 10px', color: 'var(--subtext)' }}>{s.total}</td>
                      <td style={{ padding: '5px 10px', color: rate >= 80 ? '#4ade80' : rate >= 50 ? '#fbbf24' : '#f87171' }}>
                        {rate.toFixed(0)}%
                      </td>
                      <td style={{ padding: '5px 10px', color: 'var(--subtext)' }}>{s.avg_items.toFixed(1)}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {data.strategies.length > 0 && (
        <div>
          <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
            Strategy Usage
          </div>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
              <thead>
                <tr>
                  <th style={thStyle}>Strategy</th>
                  <th style={thStyle}>Uses</th>
                  <th style={thStyle}>Avg Score</th>
                </tr>
              </thead>
              <tbody>
                {data.strategies.map((s, i) => (
                  <tr key={s.strategy} style={{ background: i % 2 === 0 ? 'var(--panel)' : 'var(--panel2)' }}>
                    <td style={{ padding: '5px 10px', color: 'var(--text)' }}>{s.strategy}</td>
                    <td style={{ padding: '5px 10px', color: 'var(--subtext)' }}>{s.uses}</td>
                    <td style={{ padding: '5px 10px', color: 'var(--subtext)' }}>{s.avg_score.toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </section>
  )
}

function RunHistorySection({ runs }: { runs: RunHistoryItem[] }) {
  const recent = runs.slice(0, 20)
  return (
    <section style={{ marginBottom: 28 }}>
      <h2 style={sectionHeadStyle}>Recent Runs</h2>
      {recent.length === 0 ? (
        <p style={{ fontSize: 12, color: 'var(--muted)' }}>No runs recorded yet.</p>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
            <thead>
              <tr>
                <th style={thStyle}>Query</th>
                <th style={thStyle}>Status</th>
                <th style={thStyle}>Duration</th>
                <th style={thStyle}>Started</th>
              </tr>
            </thead>
            <tbody>
              {recent.map((r, i) => (
                <tr key={r.id} style={{ background: i % 2 === 0 ? 'var(--panel)' : 'var(--panel2)' }}>
                  <td style={{ padding: '5px 10px', color: 'var(--text)', maxWidth: 280 }}>
                    <span
                      title={r.query}
                      style={{ display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                    >
                      {r.query}
                    </span>
                  </td>
                  <td style={{ padding: '5px 10px' }}>
                    <StatusBadge status={r.status} />
                  </td>
                  <td style={{ padding: '5px 10px', color: 'var(--subtext)', whiteSpace: 'nowrap' }}>
                    {r.duration_seconds != null ? `${r.duration_seconds.toFixed(1)}s` : '—'}
                  </td>
                  <td style={{ padding: '5px 10px', color: 'var(--muted)', whiteSpace: 'nowrap' }}>
                    {new Date(r.started_at).toLocaleString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

export default function PerformanceDashboard() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['performance-dashboard'],
    queryFn: getPerformanceDashboard,
    staleTime: 60_000,
  })

  const { data: metricsSummary, isLoading: metricsLoading } = useQuery({
    queryKey: ['metrics-summary'],
    queryFn: () => getMetricsSummary(30),
    staleTime: 60_000,
  })

  const { data: runHistory, isLoading: runsLoading } = useQuery({
    queryKey: ['run-history'],
    queryFn: () => getRunHistory(50),
    staleTime: 60_000,
  })

  if (isLoading || metricsLoading || runsLoading) {
    return (
      <div style={{ padding: 24, color: 'var(--muted)', fontSize: 12 }}>
        Loading performance data…
      </div>
    )
  }

  if (error || !data) {
    return (
      <div style={{ padding: 24, color: '#f87171', fontSize: 12 }}>
        Failed to load dashboard.
      </div>
    )
  }

  if (data.error) {
    return (
      <div style={{ padding: 24, color: '#f87171', fontSize: 12 }}>
        {data.error}
      </div>
    )
  }

  return (
    <div style={{ padding: 16, color: 'var(--text)' }}>
      {/* Metrics summary — run stats, latency, top nodes, strategy usage */}
      {metricsSummary && <MetricsSummarySection data={metricsSummary} />}

      {/* Recent run history */}
      {runHistory && <RunHistorySection runs={runHistory} />}

      {/* Technique/tactic leaderboard (existing) */}
      <div
        style={{
          display: 'flex',
          gap: 24,
          marginBottom: 20,
          fontSize: 12,
          color: 'var(--subtext)',
        }}
      >
        <span>
          <strong style={{ color: 'var(--accent)' }}>{data.total_runs}</strong> runs analysed
        </span>
        <span>
          <strong style={{ color: 'var(--text)' }}>{data.techniques.length}</strong> tools tracked
        </span>
        <span>
          <strong style={{ color: 'var(--text)' }}>{data.tactics.length}</strong> tactics tracked
        </span>
      </div>

      <section style={{ marginBottom: 32 }}>
        <h2 style={{ ...sectionHeadStyle, marginBottom: 8 }}>Tool Leaderboard</h2>
        {data.techniques.length === 0 ? (
          <p style={{ fontSize: 12, color: 'var(--muted)' }}>No technique data yet.</p>
        ) : (
          <TechniqueTable rows={data.techniques} />
        )}
      </section>

      <section>
        <h2 style={{ ...sectionHeadStyle, marginBottom: 8 }}>Tactic Summary</h2>
        {data.tactics.length === 0 ? (
          <p style={{ fontSize: 12, color: 'var(--muted)' }}>No tactic data yet.</p>
        ) : (
          <TacticTable rows={data.tactics} />
        )}
      </section>
    </div>
  )
}
