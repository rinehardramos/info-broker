import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { listNodeTypes } from '../api/pipelines'
import { getPipelineNodeEnabled, setPipelineNodeEnabled } from '../api/v3'
import IconRail from '../components/layout/IconRail'

const TAG_COLORS: Record<string, { bg: string; text: string }> = {
  source:  { bg: '#1e3a5f', text: '#60a5fa' },
  enrich:  { bg: '#2d1f4e', text: '#a78bfa' },
  score:   { bg: '#1a3a2a', text: '#4ade80' },
}

export default function NodePluginPage() {
  const { nodeType } = useParams<{ nodeType: string }>()
  const navigate = useNavigate()
  const qc = useQueryClient()

  const { data: nodeTypes = [] } = useQuery({ queryKey: ['nodeTypes'], queryFn: listNodeTypes })
  const nt = nodeTypes.find(n => n.node_type === nodeType)

  const { data: enabledData } = useQuery({
    queryKey: ['plugin-enabled', nodeType],
    queryFn: () => getPipelineNodeEnabled(nodeType!).catch(() => ({ node_type: nodeType!, enabled: true })),
    enabled: !!nodeType,
  })
  const isEnabled = enabledData?.enabled !== false

  const toggleMutation = useMutation({
    mutationFn: (next: boolean) => setPipelineNodeEnabled(nodeType!, next),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['plugin-enabled', nodeType] })
      qc.invalidateQueries({ queryKey: ['nodeTypes'] })
    },
  })

  const catColors = TAG_COLORS[nt?.category ?? ''] ?? { bg: '#1e293b', text: '#94a3b8' }

  return (
    <div className="flex h-screen" style={{ background: 'var(--bg)', color: 'var(--text)' }}>
      <div className="flex-1 flex flex-col overflow-hidden">
        <div style={{ padding: '14px 20px', borderBottom: '1px solid var(--border)' }}>
          <button
            onClick={() => navigate('/plugins')}
            style={{
              fontSize: 10,
              color: 'var(--muted)',
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              paddingBottom: 8,
              display: 'block',
            }}
          >
            ← Plugins
          </button>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <h1 style={{ fontSize: 15, fontWeight: 700, margin: 0 }}>{nt?.display_name ?? nodeType}</h1>
              {nt && (
                <span
                  style={{
                    fontSize: 9,
                    fontWeight: 700,
                    padding: '2px 6px',
                    borderRadius: 4,
                    background: catColors.bg,
                    color: catColors.text,
                    letterSpacing: '0.05em',
                  }}
                >
                  {nt.category.toUpperCase()}
                </span>
              )}
            </div>
            <button
              onClick={() => toggleMutation.mutate(!isEnabled)}
              disabled={toggleMutation.isPending}
              style={{
                fontSize: 11,
                fontWeight: 600,
                padding: '5px 14px',
                borderRadius: 20,
                border: `1px solid ${isEnabled ? '#22c55e' : '#475569'}`,
                background: isEnabled ? '#14532d33' : 'transparent',
                color: isEnabled ? '#22c55e' : '#64748b',
                cursor: 'pointer',
              }}
            >
              {isEnabled ? 'Enabled' : 'Disabled'}
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-auto" style={{ padding: 20 }}>
          {!nt && <p style={{ color: 'var(--muted)', fontSize: 12 }}>Node type not found.</p>}
          {nt && (
            <section>
              <h2
                style={{
                  fontSize: 10,
                  fontWeight: 700,
                  color: 'var(--muted)',
                  letterSpacing: '0.08em',
                  marginBottom: 8,
                }}
              >
                CONFIG SCHEMA
              </h2>
              <pre
                style={{
                  fontSize: 10,
                  color: 'var(--subtext)',
                  background: 'var(--panel)',
                  padding: 12,
                  borderRadius: 6,
                  border: '1px solid var(--border)',
                  overflow: 'auto',
                }}
              >
                {JSON.stringify(nt.config_schema, null, 2)}
              </pre>
            </section>
          )}
        </div>
      </div>
      <IconRail />
    </div>
  )
}
