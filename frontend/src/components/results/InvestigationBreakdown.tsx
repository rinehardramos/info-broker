import { useEffect, useState } from 'react'
import { GradeBadge } from './GradeBadge'
import { getScorecard, submitScorecardGrade } from '../../api/v3'
import { getPipelineRun } from '../../api/pipelines'

const SOURCE_LABELS: Record<string, string> = {
  A: 'Completely reliable', B: 'Usually reliable', C: 'Fairly reliable',
  D: 'Not usually reliable', E: 'Unreliable', F: 'Cannot be judged',
}
const CRED_LABELS: Record<string, string> = {
  '1': 'Confirmed', '2': 'Probably true', '3': 'Possibly true',
  '4': 'Doubtful', '5': 'Improbable', '6': 'Cannot be judged',
}
const SOURCE_COLORS: Record<string, string> = {
  A: '#22c55e', B: '#4ade80', C: '#facc15', D: '#fb923c', E: '#f87171', F: '#6b7280',
}

function parseGrade(g: string | null | undefined): [string, string] {
  if (!g) return ['F', '6']
  if (g.length === 2 && 'ABCDEF'.includes(g[0]) && '123456'.includes(g[1])) return [g[0], g[1]]
  if (g.length === 1 && 'ABCDEF'.includes(g[0])) return [g[0], '3']
  return ['F', '6']
}

function AdmiraltyLabel({ grade }: { grade: string | null }) {
  const [src, cred] = parseGrade(grade)
  const color = SOURCE_COLORS[src] || '#6b7280'
  return (
    <span style={{ fontSize: 9, color: '#475569' }}>
      <span style={{ color, fontWeight: 600 }}>{src}{cred}</span>
      {' — '}
      {SOURCE_LABELS[src]}, {CRED_LABELS[cred]}
    </span>
  )
}

interface Props { runId: string }

const OPEN_Q_ICONS: Record<string, string> = {
  confirmed_absent:    '●',
  provisionally_absent:'◐',
  needs_tool:          '○',
  needs_clarification: '○',
}
const OPEN_Q_COLORS: Record<string, string> = {
  confirmed_absent:    '#6b7280',
  provisionally_absent:'#94a3b8',
  needs_tool:          '#fb923c',
  needs_clarification: '#60a5fa',
}

function DeceptionPanel({ analysis }: { analysis: any }) {
  const [open, setOpen] = useState(false)

  const risk: number = analysis?.deception_risk ?? 0
  const flags: string[] = analysis?.deception_flags ?? []
  const conflicts: Array<{ dimension: string; hypotheses: string[]; evidence: any[] }> =
    analysis?.conflicts ?? []

  const hasSignal = risk > 0 || conflicts.length > 0
  if (!hasSignal) return null

  const borderColor = risk > 0.5 ? '#f87171' : risk >= 0.3 ? '#facc15' : '#4ade80'
  const riskPct = Math.round(risk * 100)
  const riskColor = risk > 0.5 ? '#f87171' : risk >= 0.3 ? '#facc15' : '#4ade80'
  const isWarning = risk > 0.3 || conflicts.length > 0

  return (
    <div style={{
      marginBottom: 10,
      border: `1px solid ${borderColor}`,
      borderRadius: 6,
      overflow: 'hidden',
    }}>
      {/* Collapsed header — always visible */}
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '6px 10px',
          background: `${borderColor}11`,
          border: 'none', cursor: 'pointer',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{ fontSize: 10, color: borderColor }}>
            {open ? '▼' : '▶'}
          </span>
          <span style={{ fontSize: 10, fontWeight: 700, color: borderColor, letterSpacing: '0.04em' }}>
            {isWarning ? '⚠ SOURCE INTEGRITY' : '✓ SOURCE INTEGRITY'}
          </span>
        </div>
        <span style={{ fontSize: 10, fontWeight: 700, color: riskColor }}>
          risk: {riskPct}%
        </span>
      </button>

      {open && (
        <div style={{ padding: '8px 10px', fontSize: 10, color: 'var(--text)' }}>
          {/* Flags */}
          {flags.length > 0 && (
            <div style={{ marginBottom: 6 }}>
              <span style={{ fontSize: 9, color: 'var(--muted)', fontWeight: 600 }}>Flags: </span>
              {flags.map((flag, i) => (
                <span key={i} style={{
                  display: 'inline-block', marginRight: 4, padding: '1px 5px', borderRadius: 3,
                  background: 'var(--panel2)', border: '1px solid var(--border)',
                  fontSize: 9, color: '#94a3b8',
                }}>
                  {flag}
                </span>
              ))}
            </div>
          )}

          {/* Conflicts */}
          {conflicts.length > 0 && (
            <div>
              <div style={{ fontSize: 9, color: 'var(--muted)', fontWeight: 600, marginBottom: 4 }}>
                Conflicts detected:
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
                {conflicts.map((c, i) => {
                  const hyps = (c.hypotheses ?? []).slice(0, 2).join('" vs "')
                  const srcCount = (c.evidence ?? []).length
                  return (
                    <div key={i} style={{ display: 'flex', gap: 5, alignItems: 'baseline' }}>
                      <span style={{ color: riskColor, flexShrink: 0 }}>•</span>
                      <span>
                        <span style={{ color: 'var(--subtext)', fontWeight: 600 }}>{c.dimension}</span>
                        {hyps && (
                          <span style={{ color: 'var(--muted)' }}>
                            {': "'}
                            {hyps}
                            {'"'}
                            {srcCount > 0 && (
                              <span style={{ fontSize: 9, color: '#94a3b8' }}>
                                {' '}({srcCount} source{srcCount !== 1 ? 's' : ''})
                              </span>
                            )}
                          </span>
                        )}
                      </span>
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {/* Clean signal */}
          {flags.length === 0 && conflicts.length === 0 && (
            <span style={{ color: '#4ade80' }}>No deception signals detected.</span>
          )}
        </div>
      )}
    </div>
  )
}

function IntelMetadata({ research }: { research: any }) {
  const [assumptionsOpen, setAssumptionsOpen] = useState(false)
  const [openQsOpen, setOpenQsOpen] = useState(false)

  const hasPir        = !!research?.pir_answered
  const hasAssumptions = (research?.working_assumptions?.length ?? 0) > 0
  const hasOpenQs     = (research?.open_questions?.length ?? 0) > 0

  if (!hasPir && !hasAssumptions && !hasOpenQs) return null

  return (
    <div style={{ marginBottom: 10, display: 'flex', flexDirection: 'column', gap: 6 }}>
      {/* PIR */}
      {hasPir && (
        <div style={{
          borderLeft: '3px solid #a78bfa',
          paddingLeft: 8, paddingTop: 5, paddingBottom: 5,
          background: 'var(--panel2)', borderRadius: '0 4px 4px 0',
        }}>
          <div style={{ fontSize: 8, fontWeight: 700, color: '#a78bfa', marginBottom: 2, letterSpacing: '0.05em' }}>
            QUESTION ANSWERED
          </div>
          <div style={{ fontSize: 10, color: 'var(--text)', lineHeight: 1.4 }}>
            {research.pir_answered}
          </div>
        </div>
      )}

      {/* Working assumptions */}
      {hasAssumptions && (
        <div>
          <button
            onClick={() => setAssumptionsOpen(o => !o)}
            style={{
              background: 'none', border: 'none', cursor: 'pointer',
              display: 'flex', alignItems: 'center', gap: 4,
              fontSize: 9, color: 'var(--muted)', fontWeight: 600,
            }}
          >
            <span>{assumptionsOpen ? '▼' : '▶'}</span>
            <span>ASSUMPTIONS ({research.working_assumptions.length})</span>
          </button>
          {assumptionsOpen && (
            <ul style={{ margin: '4px 0 0 12px', padding: 0, listStyle: 'disc', fontSize: 9, color: 'var(--muted)', lineHeight: 1.5 }}>
              {research.working_assumptions.map((a: string, i: number) => (
                <li key={i}>{a}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* Open questions */}
      {hasOpenQs && (
        <div>
          <button
            onClick={() => setOpenQsOpen(o => !o)}
            style={{
              background: 'none', border: 'none', cursor: 'pointer',
              display: 'flex', alignItems: 'center', gap: 4,
              fontSize: 9, color: 'var(--muted)', fontWeight: 600,
            }}
          >
            <span>{openQsOpen ? '▼' : '▶'}</span>
            <span>OPEN QUESTIONS ({research.open_questions.length})</span>
          </button>
          {openQsOpen && (
            <div style={{ marginTop: 4, display: 'flex', flexDirection: 'column', gap: 3 }}>
              {research.open_questions.map((q: any, i: number) => {
                const icon  = OPEN_Q_ICONS[q.status]  ?? '○'
                const color = OPEN_Q_COLORS[q.status] ?? '#94a3b8'
                return (
                  <div key={i} style={{ display: 'flex', alignItems: 'baseline', gap: 5, fontSize: 9 }}>
                    <span style={{ color, flexShrink: 0 }}>{icon}</span>
                    <span style={{ color: 'var(--muted)', fontSize: 8, flexShrink: 0 }}>{q.status.replace(/_/g, ' ')}</span>
                    <span style={{ color: 'var(--text)' }}>{q.question}</span>
                    {q.note && (
                      <span style={{ color: 'var(--muted)', fontSize: 8, fontStyle: 'italic', marginLeft: 2 }}>
                        "{q.note}"
                      </span>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export function InvestigationBreakdown({ runId }: Props) {
  const [scorecard, setScorecard] = useState<any>(null)
  const [research, setResearch] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [expanded, setExpanded] = useState(false)

  useEffect(() => {
    setLoading(true)
    getScorecard(runId)
      .then(data => { setScorecard(data); setLoading(false) })
      .catch(() => setLoading(false))
  }, [runId])

  useEffect(() => {
    if (!runId) return
    getPipelineRun(runId)
      .then(run => { if (run.research) setResearch(run.research) })
      .catch(() => {})
  }, [runId])

  if (loading) {
    return (
      <div style={{ marginTop: 12, border: '1px solid var(--border)', borderRadius: 8, padding: '8px 12px', fontSize: 11, color: 'var(--muted)' }}>
        Loading investigation breakdown…
      </div>
    )
  }

  if (!scorecard) {
    return (
      <div style={{ marginTop: 12, border: '1px solid var(--border)', borderRadius: 8, padding: '8px 12px', fontSize: 11, color: 'var(--muted)' }}>
        No scorecard available for this run.
      </div>
    )
  }

  const { strategy, tactics } = scorecard

  const handleGrade = async (level: string, name: string, grade: string) => {
    await submitScorecardGrade(runId, level as any, name, grade)
    const updated = await getScorecard(runId)
    if (updated) setScorecard(updated)
  }

  const [strategySrc] = parseGrade(strategy.user_grade || strategy.auto_grade)

  return (
    <div style={{ marginTop: 12, border: '1px solid var(--border)', borderRadius: 8, overflow: 'hidden' }}>
      {/* Header */}
      <button
        onClick={() => setExpanded(e => !e)}
        style={{
          width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '8px 12px',
          background: 'var(--panel2)', border: 'none', cursor: 'pointer',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 10, color: 'var(--muted)' }}>{expanded ? '▼' : '▶'}</span>
          <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--text)' }}>Investigation Breakdown</span>
          <span style={{ fontSize: 9, color: 'var(--muted)', fontWeight: 400 }}>NATO Admiralty</span>
        </div>
        <GradeBadge
          autoGrade={strategy.auto_grade}
          userGrade={strategy.user_grade}
          onGrade={g => handleGrade('strategy', strategy.name, g)}
          size="md"
        />
      </button>

      {expanded && (
        <div style={{ padding: '10px 12px', background: 'var(--panel)', fontSize: 11 }}>

          {/* Deception risk / ACH conflict signals */}
          <DeceptionPanel analysis={research?.analysis} />

          {/* Intelligence metadata (PIR / assumptions / open questions) */}
          <IntelMetadata research={research} />

          {/* Legend */}
          <div style={{
            display: 'flex', gap: 16, marginBottom: 10, padding: '6px 8px',
            background: 'var(--panel2)', borderRadius: 6, border: '1px solid var(--border)',
            fontSize: 9, color: 'var(--muted)',
          }}>
            <span><strong style={{ color: 'var(--text)' }}>Source A→F:</strong> Completely reliable → Cannot judge</span>
            <span><strong style={{ color: 'var(--text)' }}>Info 1→6:</strong> Confirmed → Cannot judge</span>
          </div>

          {/* Strategy row */}
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8, marginBottom: 10, padding: '8px', background: 'var(--panel2)', borderRadius: 6 }}>
            <GradeBadge
              autoGrade={strategy.auto_grade}
              userGrade={strategy.user_grade}
              onGrade={g => handleGrade('strategy', strategy.name, g)}
              size="md"
            />
            <div style={{ flex: 1 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ fontWeight: 700, color: SOURCE_COLORS[strategySrc] || 'var(--text)', fontSize: 12 }}>
                  STRATEGY: {strategy.name.toUpperCase()}
                </span>
                <span style={{ fontSize: 9, color: 'var(--muted)' }}>
                  Coverage: {Math.round((strategy.completeness_pct ?? 0) * 100)}%
                </span>
              </div>
              <AdmiraltyLabel grade={strategy.user_grade || strategy.auto_grade} />
              {strategy.comment && (
                <div style={{ fontSize: 10, color: 'var(--muted)', fontStyle: 'italic', marginTop: 3 }}>
                  {strategy.comment}
                </div>
              )}
            </div>
          </div>

          {/* Tactics */}
          {(tactics ?? []).map((tactic: any, i: number) => {
            const [tacSrc] = parseGrade(tactic.user_grade || tactic.auto_grade)
            return (
              <div key={i} style={{
                marginBottom: 8, borderLeft: `2px solid ${SOURCE_COLORS[tacSrc] || '#334155'}`,
                paddingLeft: 8,
              }}>
                {/* Tactic header */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                  <GradeBadge
                    autoGrade={tactic.auto_grade}
                    userGrade={tactic.user_grade}
                    onGrade={g => handleGrade('tactic', tactic.name, g)}
                  />
                  <span style={{ fontWeight: 600, color: 'var(--text)', fontSize: 11 }}>
                    {tactic.name.replace(/_/g, ' ')}
                  </span>
                  <span style={{ fontSize: 9, color: 'var(--muted)' }}>
                    yield {Math.round((tactic.yield_rate ?? 0) * 100)}%
                  </span>
                </div>
                <AdmiraltyLabel grade={tactic.user_grade || tactic.auto_grade} />
                {tactic.comment && (
                  <div style={{ fontSize: 10, color: 'var(--muted)', fontStyle: 'italic', marginTop: 2, marginBottom: 4 }}>
                    {tactic.comment}
                  </div>
                )}

                {/* Techniques */}
                <div style={{ paddingLeft: 8, display: 'flex', flexDirection: 'column', gap: 3, marginTop: 4 }}>
                  {(tactic.techniques ?? []).map((tech: any, j: number) => {
                    const [techSrc] = parseGrade(tech.user_grade || tech.auto_grade)
                    return (
                      <div key={j} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <GradeBadge
                          autoGrade={tech.auto_grade}
                          userGrade={tech.user_grade}
                          onGrade={g => handleGrade('technique', tech.tool, g)}
                        />
                        <span style={{ fontFamily: 'monospace', fontSize: 10, color: SOURCE_COLORS[techSrc] || 'var(--muted)' }}>
                          {tech.tool.replace('mcp__info-broker-mcp__', '')}
                        </span>
                        <span style={{ fontSize: 9, color: 'var(--muted)' }}>
                          {tech.result_count > 0
                            ? `${tech.result_count} found`
                            : tech.error ? 'error' : 'none'}
                        </span>
                        {tech.comment && (
                          <span style={{ fontSize: 9, color: '#475569', fontStyle: 'italic' }}>
                            {tech.comment}
                          </span>
                        )}
                      </div>
                    )
                  })}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
