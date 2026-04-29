import { useState } from 'react'
import { PipelineNodeOut } from '../../api/pipelines'

interface Props {
  node: PipelineNodeOut
  schema: Record<string, unknown>
  onChange: (nodeId: string, config: Record<string, unknown>) => void
  onClose: () => void
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

export function NodeConfigForm({ node, schema, onChange, onClose }: Props) {
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
                <label style={{ display: 'block', fontSize: 11, color: '#94a3b8', marginBottom: 4 }}>{label}</label>
                <input
                  type="number"
                  value={(value ?? field.default ?? '') as number}
                  min={field.minimum}
                  max={field.maximum}
                  onChange={e => update(key, Number(e.target.value))}
                  style={{ width: '100%', padding: '6px 8px', background: '#1e293b', border: '1px solid #334155', borderRadius: 4, color: '#e2e8f0', fontSize: 12, boxSizing: 'border-box' }}
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
                  style={{ width: '100%', padding: '6px 8px', background: '#1e293b', border: '1px solid #334155', borderRadius: 4, color: '#e2e8f0', fontSize: 12, boxSizing: 'border-box' }}
                />
              </div>
            )
          }

          // default: string
          return (
            <div key={key} style={{ marginBottom: 12 }}>
              <label style={{ display: 'block', fontSize: 11, color: '#94a3b8', marginBottom: 4 }}>{label}</label>
              <input
                type="text"
                value={(value ?? field.default ?? '') as string}
                onChange={e => update(key, e.target.value)}
                style={{ width: '100%', padding: '6px 8px', background: '#1e293b', border: '1px solid #334155', borderRadius: 4, color: '#e2e8f0', fontSize: 12, boxSizing: 'border-box' }}
              />
            </div>
          )
        })}

        <button
          onClick={onClose}
          style={{ width: '100%', padding: '8px', marginTop: 8, background: '#1e293b', border: '1px solid #334155', borderRadius: 4, color: '#e2e8f0', cursor: 'pointer', fontSize: 12 }}
        >
          Done
        </button>
      </div>
    </div>
  )
}
