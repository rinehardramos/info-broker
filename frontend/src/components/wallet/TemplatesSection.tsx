/**
 * TemplatesSection — Enhancement 3.2
 *
 * Renders the list of saved templates on the Wallet page.
 * Provides delete and usage stats per template.
 */
import { useState } from 'react'
import { useTemplates } from '../../hooks/useTemplates'
import type { Template } from '../../hooks/useTemplates'

function _relativeTime(iso: string | null): string {
  if (!iso) return 'never'
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

function _formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString()
}

interface TemplateRowProps {
  template: Template
  onDelete: (id: string) => void
}

function TemplateRow({ template: t, onDelete }: TemplateRowProps) {
  const [confirming, setConfirming] = useState(false)

  return (
    <div
      style={{
        padding: '10px 14px',
        borderBottom: '1px solid var(--border)',
        display: 'flex',
        flexDirection: 'column',
        gap: 4,
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <span style={{ fontWeight: 600, fontSize: 13 }}>{t.name}</span>
          <span
            style={{
              marginLeft: 8,
              fontSize: 10,
              background: 'var(--accent)',
              color: '#fff',
              borderRadius: 3,
              padding: '1px 6px',
            }}
          >
            {t.strategy_id}
          </span>
        </div>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          {confirming ? (
            <>
              <span style={{ fontSize: 11, color: 'var(--muted)' }}>Delete?</span>
              <button
                onClick={() => onDelete(t.id)}
                style={{
                  fontSize: 11,
                  padding: '2px 8px',
                  borderRadius: 3,
                  border: '1px solid #c00',
                  color: '#c00',
                  background: 'transparent',
                  cursor: 'pointer',
                }}
              >
                Yes
              </button>
              <button
                onClick={() => setConfirming(false)}
                style={{
                  fontSize: 11,
                  padding: '2px 8px',
                  borderRadius: 3,
                  border: '1px solid var(--border)',
                  background: 'transparent',
                  color: 'var(--foreground)',
                  cursor: 'pointer',
                }}
              >
                No
              </button>
            </>
          ) : (
            <button
              onClick={() => setConfirming(true)}
              title="Delete template"
              style={{
                fontSize: 11,
                padding: '2px 8px',
                borderRadius: 3,
                border: '1px solid var(--border)',
                background: 'transparent',
                color: 'var(--muted)',
                cursor: 'pointer',
              }}
            >
              Delete
            </button>
          )}
        </div>
      </div>

      {/* Query preview */}
      <div
        style={{
          fontSize: 11,
          color: 'var(--muted)',
          whiteSpace: 'nowrap',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
        }}
      >
        {t.query}
      </div>

      {/* Usage stats */}
      <div style={{ fontSize: 10, color: 'var(--muted)', display: 'flex', gap: 12 }}>
        <span>Used {t.use_count}x</span>
        <span>Last used: {_relativeTime(t.last_used)}</span>
        <span>Created: {_formatDate(t.created_at)}</span>
      </div>

      {/* Envelope chips */}
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 2 }}>
        {Object.entries(t.envelope)
          .filter(([, v]) => v)
          .map(([k, v]) => (
            <span
              key={k}
              style={{
                fontSize: 9,
                padding: '1px 6px',
                borderRadius: 3,
                border: '1px solid var(--border)',
                color: 'var(--muted)',
              }}
            >
              {k}: {v}
            </span>
          ))}
      </div>
    </div>
  )
}

export function TemplatesSection() {
  const { templates, isLoading, error, deleteTemplate } = useTemplates()

  return (
    <div
      style={{
        background: 'var(--panel)',
        border: '1px solid var(--border)',
        borderRadius: 12,
        padding: '20px 24px',
      }}
    >
      <h2 style={{ fontSize: 14, fontWeight: 600, marginTop: 0, marginBottom: 12 }}>
        Saved Templates
      </h2>

      {error && (
        <div style={{ fontSize: 12, color: '#c00', marginBottom: 8 }}>{error}</div>
      )}

      {isLoading && (
        <div style={{ fontSize: 12, color: 'var(--muted)' }}>Loading templates…</div>
      )}

      {!isLoading && templates.length === 0 && (
        <div style={{ fontSize: 12, color: 'var(--muted)' }}>
          No templates saved yet. Run a preflight and save your settings as a template.
        </div>
      )}

      {!isLoading && templates.length > 0 && (
        <div style={{ border: '1px solid var(--border)', borderRadius: 6, overflow: 'hidden' }}>
          {templates.map(t => (
            <TemplateRow
              key={t.id}
              template={t}
              onDelete={deleteTemplate}
            />
          ))}
        </div>
      )}
    </div>
  )
}
