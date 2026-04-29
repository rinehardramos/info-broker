import { useState } from 'react'
import { PipelineNodeOut, PipelineEdgeOut } from '../../api/pipelines'

const CATEGORY_COLORS: Record<string, string> = {
  source: '#60a5fa',
  enrich: '#a78bfa',
  score: '#4ade80',
  filter: '#fb923c',
}

interface Props {
  node: PipelineNodeOut
  schema: Record<string, unknown>
  onChange: (nodeId: string, config: Record<string, unknown>) => void
  onClose: () => void   // ✕ button — discard / just close
  onDone?: () => void   // Done button — close + save
  nodes?: PipelineNodeOut[]
  edges?: PipelineEdgeOut[]
  onEdgeChange?: (sourceId: string, targetId: string, connected: boolean) => void
}

type FieldSchema = {
  type?: string
  title?: string
  enum?: string[]
  default?: unknown
  minimum?: number
  maximum?: number
  format?: string
  items?: { type?: string }
}

export function NodeConfigForm({ node, schema, onChange, onClose, onDone, nodes, edges, onEdgeChange }: Props) {
  const properties = (schema.properties ?? {}) as Record<string, FieldSchema>
  const required = (schema.required ?? []) as string[]
  const [config, setConfig] = useState<Record<string, unknown>>({ ...node.config })

  const update = (key: string, value: unknown) => {
    const next = { ...config, [key]: value }
    setConfig(next)
    onChange(node.id, next)
  }

  return (
    <div
      style={{
        position: 'absolute',
        inset: 0,
        background: 'rgba(0,0,0,0.6)',
        display: 'flex',
        alignItems: 'flex-start',
        justifyContent: 'flex-end',
        zIndex: 100,
      }}
      onClick={onClose}
    >
      <div
        style={{
          width: 320,
          height: '100%',
          background: '#0d1117',
          borderLeft: '1px solid #1e293b',
          padding: 16,
          overflowY: 'auto',
        }}
        onClick={e => e.stopPropagation()}
        data-testid="node-config-panel"
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
          <span style={{ color: '#e2e8f0', fontWeight: 600 }}>{node.label}</span>
          <button
            onClick={onClose}
            style={{ background: 'transparent', border: 'none', color: '#94a3b8', cursor: 'pointer', fontSize: 16 }}
          >
            ✕
          </button>
        </div>

        {Object.entries(properties).map(([key, field]) => {
          const value = config[key]
          const isRequired = required.includes(key)
          const label = `${field.title ?? key}${isRequired ? ' *' : ''}`
          // A required field is invalid when it has no value AND no schema default AND is not an enum
          const isEmpty = value === undefined || value === null || value === ''
          const fieldInvalid = isRequired && isEmpty && field.default === undefined && !field.enum
          const inputBorder = `1px solid ${fieldInvalid ? '#ef4444' : '#334155'}`

          if (field.enum) {
            return (
              <div key={key} style={{ marginBottom: 12 }}>
                <label style={{ display: 'block', fontSize: 11, color: '#94a3b8', marginBottom: 4 }}>{label}</label>
                <select
                  value={(value ?? field.default ?? '') as string}
                  onChange={e => update(key, e.target.value)}
                  style={{ width: '100%', padding: '6px 8px', background: '#1e293b', border: '1px solid #334155', borderRadius: 4, color: '#e2e8f0', fontSize: 12 }}
                >
                  {field.enum.map(opt => <option key={opt} value={opt}>{opt}</option>)}
                </select>
              </div>
            )
          }

          if (field.type === 'boolean') {
            return (
              <div key={key} style={{ marginBottom: 12, display: 'flex', alignItems: 'center', gap: 8 }}>
                <input
                  type="checkbox"
                  checked={!!(value ?? field.default)}
                  onChange={e => update(key, e.target.checked)}
                />
                <label style={{ fontSize: 11, color: '#94a3b8' }}>{label}</label>
              </div>
            )
          }

          if (field.type === 'integer' || field.type === 'number') {
            return (
              <div key={key} style={{ marginBottom: 12 }}>
                <label style={{ display: 'block', fontSize: 11, color: fieldInvalid ? '#f87171' : '#94a3b8', marginBottom: 4 }}>{label}</label>
                <input
                  type="number"
                  value={(value ?? field.default ?? '') as number}
                  min={field.minimum}
                  max={field.maximum}
                  onChange={e => update(key, Number(e.target.value))}
                  style={{ width: '100%', padding: '6px 8px', background: '#1e293b', border: inputBorder, borderRadius: 4, color: '#e2e8f0', fontSize: 12, boxSizing: 'border-box' }}
                />
              </div>
            )
          }

          if (field.type === 'array') {
            const arr = Array.isArray(value) ? value : []
            return (
              <div key={key} style={{ marginBottom: 12 }}>
                <label style={{ display: 'block', fontSize: 11, color: '#94a3b8', marginBottom: 4 }}>{label} (comma-separated)</label>
                <input
                  type="text"
                  value={arr.join(', ')}
                  onChange={e => update(key, e.target.value.split(',').map(s => s.trim()).filter(Boolean))}
                  style={{ width: '100%', padding: '6px 8px', background: '#1e293b', border: inputBorder, borderRadius: 4, color: '#e2e8f0', fontSize: 12, boxSizing: 'border-box' }}
                />
              </div>
            )
          }

          // default: string
          return (
            <div key={key} style={{ marginBottom: 12 }}>
              <label style={{ display: 'block', fontSize: 11, color: fieldInvalid ? '#f87171' : '#94a3b8', marginBottom: 4 }}>{label}</label>
              <input
                type="text"
                value={(value ?? field.default ?? '') as string}
                onChange={e => update(key, e.target.value)}
                style={{ width: '100%', padding: '6px 8px', background: '#1e293b', border: inputBorder, borderRadius: 4, color: '#e2e8f0', fontSize: 12, boxSizing: 'border-box' }}
              />
            </div>
          )
        })}

        {/* Outputs — connect this node to downstream steps */}
        {nodes && nodes.filter(n => n.id !== node.id).length > 0 && (
          <div style={{ marginTop: 16, borderTop: '1px solid #1e293b', paddingTop: 12 }}>
            <div style={{ fontSize: 10, fontWeight: 700, color: '#475569', letterSpacing: '0.08em', marginBottom: 10 }}>
              OUTPUTS
            </div>
            {nodes.filter(n => n.id !== node.id).map(other => {
              const connected = edges?.some(e => e.source_node_id === node.id && e.target_node_id === other.id) ?? false
              const color = CATEGORY_COLORS[other.category] ?? '#60a5fa'
              return (
                <div key={other.id} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 0 }}>
                    <span style={{ fontSize: 8, color, flexShrink: 0 }}>●</span>
                    <span style={{ fontSize: 11, color: '#e2e8f0', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {other.label}
                    </span>
                    <span style={{ fontSize: 9, color, flexShrink: 0 }}>{other.category.toUpperCase()}</span>
                  </div>
                  <button
                    data-testid={`output-connect-${other.node_type}`}
                    onClick={() => onEdgeChange?.(node.id, other.id, !connected)}
                    style={{
                      fontSize: 10, padding: '2px 10px', borderRadius: 20, flexShrink: 0, marginLeft: 6,
                      border: `1px solid ${connected ? '#4ade80' : '#334155'}`,
                      background: connected ? '#14532d33' : 'transparent',
                      color: connected ? '#4ade80' : '#64748b',
                      cursor: 'pointer',
                    }}
                  >
                    {connected ? 'Connected' : 'Connect'}
                  </button>
                </div>
              )
            })}
          </div>
        )}

        <button
          onClick={onDone ?? onClose}
          style={{ width: '100%', padding: '8px', marginTop: 12, background: '#1e293b', border: '1px solid #334155', borderRadius: 4, color: '#e2e8f0', cursor: 'pointer', fontSize: 12 }}
        >
          Done
        </button>
      </div>
    </div>
  )
}
