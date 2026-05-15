/**
 * RunCostBreakdown — per-run RU breakdown by phase and by technique.
 * Rendered inside a side-panel when user clicks a run in the Runs page.
 *
 * by_technique is a MVP even-split placeholder — see by_technique_note
 * returned from the backend.
 *
 * TODO (post-MVP): real per-technique accounting once wallet_operations
 * tracks technique-level metadata (backend endpoint will stop using even-split).
 */
import { useRunCostBreakdown } from '@/hooks/useWallet'

interface Props {
  runId: string
}

function fmtDate(iso: string | null | undefined): string {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: 'short', day: 'numeric',
      hour: '2-digit', minute: '2-digit',
    })
  } catch {
    return iso
  }
}

export function RunCostBreakdown({ runId }: Props) {
  const { data, isLoading, isError } = useRunCostBreakdown(runId)

  if (isLoading) {
    return <div style={{ fontSize: 12, color: 'var(--muted)', padding: 16 }}>Loading cost breakdown…</div>
  }

  if (isError || !data) {
    return <div style={{ fontSize: 12, color: '#f87171', padding: 16 }}>Failed to load cost breakdown</div>
  }

  const maxPhaseRu = Math.max(...data.by_phase.map(p => p.ru_consumed), 1)

  return (
    <div style={{ padding: '0 4px', display: 'flex', flexDirection: 'column', gap: 20 }}>
      {/* Header */}
      <div>
        <div style={{ fontSize: 12, color: 'var(--muted)' }}>Run cost breakdown</div>
        <div style={{ fontSize: 28, fontWeight: 700, color: '#a78bfa', marginTop: 2 }}>
          {data.total_ru.toLocaleString()}
          <span style={{ fontSize: 14, color: 'var(--muted)', marginLeft: 4, fontWeight: 400 }}>RU</span>
        </div>
        <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 2 }}>
          {fmtDate(data.started_at)} → {fmtDate(data.completed_at)}
        </div>
      </div>

      {/* By phase */}
      {data.by_phase.length > 0 && (
        <section>
          <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 8, color: 'var(--subtext)' }}>
            By phase
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {data.by_phase.map(phase => {
              const barPct = (phase.ru_consumed / maxPhaseRu) * 100
              const label = phase.phase_id.replace('consume_', '')
              return (
                <div key={phase.phase_id}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, marginBottom: 2 }}>
                    <span style={{ color: 'var(--muted)', fontFamily: 'monospace' }}>{label}</span>
                    <span style={{ color: 'var(--text)', fontVariantNumeric: 'tabular-nums' }}>
                      {phase.ru_consumed} RU
                    </span>
                  </div>
                  <div style={{ height: 4, borderRadius: 2, background: 'var(--border)' }}>
                    <div
                      style={{
                        height: '100%',
                        width: `${barPct}%`,
                        borderRadius: 2,
                        background: '#a78bfa',
                        transition: 'width 0.3s',
                      }}
                    />
                  </div>
                </div>
              )
            })}
          </div>
        </section>
      )}

      {/* By technique (MVP placeholder) */}
      {data.by_technique.length > 0 && (
        <section>
          <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 4, color: 'var(--subtext)' }}>
            By technique
            <span
              style={{
                marginLeft: 6,
                fontSize: 10,
                color: '#f59e0b',
                background: 'rgba(245,158,11,0.1)',
                border: '1px solid rgba(245,158,11,0.3)',
                borderRadius: 4,
                padding: '1px 5px',
              }}
            >
              est.
            </span>
          </div>
          <div style={{ fontSize: 10, color: 'var(--muted)', marginBottom: 8 }}>
            Even-split estimate — real per-technique accounting is post-MVP
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {data.by_technique.map(t => (
              <div key={t.technique_id} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11 }}>
                <span style={{ color: 'var(--muted)', fontFamily: 'monospace' }}>{t.technique_id}</span>
                <span style={{ color: 'var(--text)', fontVariantNumeric: 'tabular-nums' }}>
                  ~{t.ru_estimate} RU
                </span>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Wallet operations */}
      {data.wallet_operations.length > 0 && (
        <section>
          <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 8, color: 'var(--subtext)' }}>
            Wallet operations
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
            {data.wallet_operations.map((op, i) => (
              <div key={i} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11 }}>
                <span style={{ color: 'var(--muted)', fontFamily: 'monospace' }}>{String(op.op)}</span>
                <span style={{ color: 'var(--text)', fontVariantNumeric: 'tabular-nums' }}>
                  {(op.delta_ru as number) > 0 ? '+' : ''}{String(op.delta_ru)} RU
                </span>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  )
}
