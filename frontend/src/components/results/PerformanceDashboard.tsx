import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getPerformanceDashboard, TechniquePerf, TacticPerf } from '../../api/v3'

const SOURCE_COLORS: Record<string, string> = {
  A: '#22c55e', B: '#4ade80', C: '#facc15', D: '#fb923c', E: '#f87171', F: '#6b7280',
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

  const thStyle: React.CSSProperties = {}

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

export default function PerformanceDashboard() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['performance-dashboard'],
    queryFn: getPerformanceDashboard,
    staleTime: 60_000,
  })

  if (isLoading) {
    return (
      <div
        style={{ padding: 24, color: 'var(--muted)', fontSize: 12 }}
      >
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
      {/* Summary bar */}
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

      {/* Technique leaderboard */}
      <section style={{ marginBottom: 32 }}>
        <h2
          style={{
            fontSize: 12,
            fontWeight: 600,
            color: 'var(--accent)',
            marginBottom: 8,
            textTransform: 'uppercase',
            letterSpacing: '0.05em',
          }}
        >
          Tool Leaderboard
        </h2>
        {data.techniques.length === 0 ? (
          <p style={{ fontSize: 12, color: 'var(--muted)' }}>No technique data yet.</p>
        ) : (
          <TechniqueTable rows={data.techniques} />
        )}
      </section>

      {/* Tactic summary */}
      <section>
        <h2
          style={{
            fontSize: 12,
            fontWeight: 600,
            color: 'var(--accent)',
            marginBottom: 8,
            textTransform: 'uppercase',
            letterSpacing: '0.05em',
          }}
        >
          Tactic Summary
        </h2>
        {data.tactics.length === 0 ? (
          <p style={{ fontSize: 12, color: 'var(--muted)' }}>No tactic data yet.</p>
        ) : (
          <TacticTable rows={data.tactics} />
        )}
      </section>
    </div>
  )
}
