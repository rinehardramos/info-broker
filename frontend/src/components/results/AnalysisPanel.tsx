import { useState } from 'react'

interface AnalysisPanelProps {
  analysis: {
    entities?: { name: string; type: string; attributes: Record<string, string>; evidence: number[] }[]
    relationships?: { from: string; to: string; type: string; evidence: string }[]
    insights?: string[]
    recommendations?: { action: string; reason: string; priority: string }[]
    research_gaps?: { entity: string; missing: string; suggested_tool: string }[]
    enrichment_targets?: { entity: string; action: string; reason: string }[]
    error_summary?: { total_errors: number; tools_failing: string[]; action_needed: string | null }
    stats?: { findings_analyzed: number; findings_filtered_as_errors: number; entities_extracted: number; relationships_found: number }
  }
}

const PRIORITY_COLORS: Record<string, string> = {
  high: '#f87171',
  medium: '#f59e0b',
  low: '#4ade80',
}

function SectionHeader({ title }: { title: string }) {
  return (
    <div
      style={{
        fontSize: 9, fontWeight: 700, letterSpacing: '0.1em',
        color: 'var(--muted)', marginBottom: 6, marginTop: 14,
      }}
    >
      {title}
    </div>
  )
}

export function AnalysisPanel({ analysis }: AnalysisPanelProps) {
  const [expandedEntities, setExpandedEntities] = useState<Record<string, boolean>>({})

  const toggleEntity = (name: string) =>
    setExpandedEntities(prev => ({ ...prev, [name]: !prev[name] }))

  // Group entities by type
  const entityGroups: Record<string, typeof analysis.entities> = {}
  for (const e of analysis.entities ?? []) {
    if (!entityGroups[e.type]) entityGroups[e.type] = []
    entityGroups[e.type]!.push(e)
  }

  const stats = analysis.stats
  const errorSummary = analysis.error_summary

  return (
    <div
      style={{
        background: 'var(--panel2)',
        border: '1px solid var(--border)',
        borderRadius: 8,
        padding: 12,
        marginTop: 12,
        fontSize: 11,
      }}
    >
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 10 }}>
        <span style={{ color: '#f59e0b', fontSize: 12 }}>◈</span>
        <span style={{ color: '#f59e0b', fontWeight: 700, fontSize: 12 }}>Analysis</span>
      </div>

      {/* Stats bar */}
      {stats && (
        <div
          style={{
            display: 'flex', gap: 10, flexWrap: 'wrap',
            background: 'var(--panel)', border: '1px solid var(--border)',
            borderRadius: 6, padding: '6px 10px', fontSize: 10,
          }}
        >
          <span style={{ color: 'var(--subtext)' }}>
            <span style={{ color: 'var(--text)', fontWeight: 600 }}>{stats.findings_analyzed}</span> findings analyzed
          </span>
          <span style={{ color: 'var(--muted)' }}>·</span>
          <span style={{ color: 'var(--subtext)' }}>
            <span style={{ color: '#4ade80', fontWeight: 600 }}>{stats.entities_extracted}</span> entities
          </span>
          <span style={{ color: 'var(--muted)' }}>·</span>
          <span style={{ color: 'var(--subtext)' }}>
            <span style={{ color: '#60a5fa', fontWeight: 600 }}>{stats.relationships_found}</span> relationships
          </span>
          {stats.findings_filtered_as_errors > 0 && (
            <>
              <span style={{ color: 'var(--muted)' }}>·</span>
              <span style={{ color: '#f87171', fontWeight: 600 }}>{stats.findings_filtered_as_errors} errors filtered</span>
            </>
          )}
        </div>
      )}

      {/* Error Summary */}
      {errorSummary && errorSummary.total_errors > 0 && (
        <>
          <SectionHeader title="ERROR SUMMARY" />
          <div
            style={{
              background: '#f8717111', border: '1px solid #f8717133',
              borderRadius: 6, padding: '8px 10px', fontSize: 10,
            }}
          >
            <div style={{ color: '#f87171', fontWeight: 600, marginBottom: 4 }}>
              {errorSummary.total_errors} errors — {errorSummary.tools_failing.length} tools failing
            </div>
            {errorSummary.tools_failing.length > 0 && (
              <div style={{ color: 'var(--muted)', marginBottom: 4 }}>
                {errorSummary.tools_failing.join(', ')}
              </div>
            )}
            {errorSummary.action_needed && (
              <div style={{ color: '#f87171' }}>{errorSummary.action_needed}</div>
            )}
          </div>
        </>
      )}

      {/* Entities */}
      {Object.keys(entityGroups).length > 0 && (
        <>
          <SectionHeader title="ENTITIES" />
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {Object.entries(entityGroups).map(([type, entities]) => (
              <div key={type}>
                <div
                  style={{
                    fontSize: 9, fontWeight: 700, color: '#a78bfa',
                    textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 3,
                  }}
                >
                  {type}
                </div>
                {(entities ?? []).map(e => (
                  <div
                    key={e.name}
                    style={{
                      background: 'var(--panel)', border: '1px solid var(--border)',
                      borderRadius: 5, padding: '5px 8px', marginBottom: 3,
                    }}
                  >
                    <div
                      style={{
                        display: 'flex', alignItems: 'center', gap: 6,
                        cursor: Object.keys(e.attributes ?? {}).length > 0 ? 'pointer' : 'default',
                      }}
                      onClick={() => Object.keys(e.attributes ?? {}).length > 0 && toggleEntity(e.name)}
                    >
                      <span style={{ color: 'var(--text)', fontWeight: 600, flex: 1 }}>{e.name}</span>
                      {Object.keys(e.attributes ?? {}).length > 0 && (
                        <span style={{ color: 'var(--muted)', fontSize: 9 }}>
                          {expandedEntities[e.name] ? '▲' : '▼'}
                        </span>
                      )}
                    </div>
                    {expandedEntities[e.name] && Object.keys(e.attributes ?? {}).length > 0 && (
                      <div style={{ marginTop: 5, display: 'flex', flexDirection: 'column', gap: 2 }}>
                        {Object.entries(e.attributes).map(([k, v]) => (
                          <div key={k} style={{ display: 'flex', gap: 6, fontSize: 10 }}>
                            <span style={{ color: 'var(--muted)', minWidth: 80 }}>{k}</span>
                            <span style={{ color: 'var(--subtext)' }}>{v}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            ))}
          </div>
        </>
      )}

      {/* Relationships */}
      {(analysis.relationships?.length ?? 0) > 0 && (
        <>
          <SectionHeader title="RELATIONSHIPS" />
          <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
            {analysis.relationships!.map((r, i) => (
              <div
                key={i}
                style={{
                  fontSize: 10, color: 'var(--subtext)',
                  background: 'var(--panel)', border: '1px solid var(--border)',
                  borderRadius: 5, padding: '4px 8px',
                  display: 'flex', alignItems: 'center', gap: 4, flexWrap: 'wrap',
                }}
              >
                <span style={{ color: 'var(--text)', fontWeight: 600 }}>{r.from}</span>
                <span style={{ color: 'var(--muted)' }}>→</span>
                <span style={{ color: '#60a5fa' }}>{r.type}</span>
                <span style={{ color: 'var(--muted)' }}>→</span>
                <span style={{ color: 'var(--text)', fontWeight: 600 }}>{r.to}</span>
              </div>
            ))}
          </div>
        </>
      )}

      {/* Insights */}
      {(analysis.insights?.length ?? 0) > 0 && (
        <>
          <SectionHeader title="INSIGHTS" />
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {analysis.insights!.map((insight, i) => (
              <div
                key={i}
                style={{
                  display: 'flex', gap: 6, fontSize: 10,
                  color: 'var(--subtext)', lineHeight: 1.5,
                }}
              >
                <span style={{ color: '#f59e0b', flexShrink: 0, marginTop: 1 }}>•</span>
                <span>{insight}</span>
              </div>
            ))}
          </div>
        </>
      )}

      {/* Recommendations */}
      {(analysis.recommendations?.length ?? 0) > 0 && (
        <>
          <SectionHeader title="RECOMMENDATIONS" />
          <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
            {analysis.recommendations!.map((rec, i) => {
              const priorityColor = PRIORITY_COLORS[rec.priority?.toLowerCase()] ?? 'var(--muted)'
              return (
                <div
                  key={i}
                  style={{
                    background: 'var(--panel)', border: '1px solid var(--border)',
                    borderRadius: 5, padding: '6px 8px',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 3 }}>
                    <span
                      style={{
                        fontSize: 8, fontWeight: 700, padding: '1px 5px',
                        borderRadius: 3, background: `${priorityColor}22`,
                        color: priorityColor, border: `1px solid ${priorityColor}44`,
                        textTransform: 'uppercase',
                      }}
                    >
                      {rec.priority}
                    </span>
                    <span style={{ color: 'var(--text)', fontWeight: 600, fontSize: 10 }}>{rec.action}</span>
                  </div>
                  <p style={{ color: 'var(--muted)', fontSize: 10, lineHeight: 1.4, margin: 0 }}>{rec.reason}</p>
                </div>
              )
            })}
          </div>
        </>
      )}

      {/* Research Gaps */}
      {(analysis.research_gaps?.length ?? 0) > 0 && (
        <>
          <SectionHeader title="RESEARCH GAPS" />
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {analysis.research_gaps!.map((gap, i) => (
              <div
                key={i}
                style={{
                  background: 'var(--panel)', border: '1px solid var(--border)',
                  borderRadius: 5, padding: '6px 8px',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 2 }}>
                  <span style={{ color: 'var(--text)', fontWeight: 600, fontSize: 10 }}>{gap.entity}</span>
                  <span
                    style={{
                      fontSize: 8, fontWeight: 700, padding: '1px 5px', borderRadius: 3,
                      background: '#60a5fa22', color: '#60a5fa', border: '1px solid #60a5fa44',
                    }}
                  >
                    {gap.suggested_tool}
                  </span>
                </div>
                <p style={{ color: 'var(--muted)', fontSize: 10, lineHeight: 1.4, margin: 0 }}>{gap.missing}</p>
              </div>
            ))}
          </div>
        </>
      )}

      {/* Enrichment Targets */}
      {(analysis.enrichment_targets?.length ?? 0) > 0 && (
        <>
          <SectionHeader title="ENRICHMENT TARGETS" />
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {analysis.enrichment_targets!.map((target, i) => (
              <div
                key={i}
                style={{
                  background: 'var(--panel)', border: '1px solid var(--border)',
                  borderRadius: 5, padding: '6px 8px',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 2 }}>
                  <span style={{ color: 'var(--text)', fontWeight: 600, fontSize: 10 }}>{target.entity}</span>
                  <span style={{ color: '#f59e0b', fontSize: 10 }}>→ {target.action}</span>
                </div>
                <p style={{ color: 'var(--muted)', fontSize: 10, lineHeight: 1.4, margin: 0 }}>{target.reason}</p>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}
