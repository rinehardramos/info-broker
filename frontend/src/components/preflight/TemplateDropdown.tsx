/**
 * TemplateDropdown — Enhancement 3.2
 *
 * Shown at the top of PreflightPanel. Lists the user's saved templates ordered
 * by last_used DESC. Clicking a template loads its envelope + strategy into the
 * preflight form. "Save current as template…" opens SaveTemplateDialog.
 */
import { useState } from 'react'
import type { Template } from '../../hooks/useTemplates'

interface TemplateDropdownProps {
  templates: Template[]
  isLoading: boolean
  onSelect: (template: Template) => void
  onSaveRequest: () => void
}

function _relativeTime(iso: string | null): string {
  if (!iso) return 'never used'
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

export function TemplateDropdown({
  templates,
  isLoading,
  onSelect,
  onSaveRequest,
}: TemplateDropdownProps) {
  const [open, setOpen] = useState(false)

  if (isLoading) {
    return (
      <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 10 }}>
        Loading templates…
      </div>
    )
  }

  return (
    <div style={{ position: 'relative', marginBottom: 12 }}>
      <button
        onClick={() => setOpen(v => !v)}
        aria-haspopup="listbox"
        aria-expanded={open}
        style={{
          width: '100%',
          textAlign: 'left',
          padding: '5px 10px',
          fontSize: 12,
          border: '1px solid var(--border)',
          borderRadius: 6,
          background: 'var(--background)',
          color: 'var(--foreground)',
          cursor: 'pointer',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
        }}
      >
        <span style={{ color: templates.length ? 'var(--foreground)' : 'var(--muted)' }}>
          {templates.length ? 'Load a saved template…' : 'No templates saved yet'}
        </span>
        <span style={{ fontSize: 10, color: 'var(--muted)' }}>{open ? '▴' : '▾'}</span>
      </button>

      {open && (
        <ul
          role="listbox"
          style={{
            position: 'absolute',
            top: '100%',
            left: 0,
            right: 0,
            zIndex: 200,
            background: 'var(--background)',
            border: '1px solid var(--border)',
            borderRadius: 6,
            boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
            margin: 0,
            padding: '4px 0',
            listStyle: 'none',
            maxHeight: 260,
            overflowY: 'auto',
          }}
        >
          {templates.map(t => (
            <li
              key={t.id}
              role="option"
              aria-selected={false}
              onClick={() => {
                onSelect(t)
                setOpen(false)
              }}
              style={{
                padding: '7px 12px',
                cursor: 'pointer',
                fontSize: 12,
                borderBottom: '1px solid var(--border)',
              }}
              onMouseEnter={e => (e.currentTarget.style.background = 'var(--hover)')}
              onMouseLeave={e => (e.currentTarget.style.background = '')}
            >
              <div style={{ fontWeight: 600, marginBottom: 2 }}>{t.name}</div>
              <div
                style={{
                  color: 'var(--muted)',
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  maxWidth: '100%',
                  fontSize: 11,
                }}
              >
                {t.query}
              </div>
              <div style={{ fontSize: 10, color: 'var(--muted)', marginTop: 2 }}>
                {_relativeTime(t.last_used)} · used {t.use_count}x
              </div>
            </li>
          ))}

          {/* Divider + save action */}
          <li
            role="option"
            aria-selected={false}
            onClick={() => {
              onSaveRequest()
              setOpen(false)
            }}
            style={{
              padding: '7px 12px',
              cursor: 'pointer',
              fontSize: 12,
              color: 'var(--accent)',
              fontWeight: 500,
            }}
            onMouseEnter={e => (e.currentTarget.style.background = 'var(--hover)')}
            onMouseLeave={e => (e.currentTarget.style.background = '')}
          >
            + Save current as template…
          </li>
        </ul>
      )}
    </div>
  )
}
