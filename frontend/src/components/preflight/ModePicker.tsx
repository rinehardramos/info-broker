/**
 * ModePicker — 6-option mode chooser rendered as a pill row.
 *
 * Each pill shows the mode label and a 1-line description on hover (title).
 * Selecting a mode calls onSelect; the parent is responsible for applying
 * the mode's dial_defaults (passed back via the full ModeEntry).
 */
import type { ModeEntry } from '../../hooks/usePreflight'

interface ModePickerProps {
  modes: ModeEntry[]
  selectedMode: string
  onSelect: (mode: ModeEntry) => void
}

export function ModePicker({ modes, selectedMode, onSelect }: ModePickerProps) {
  if (modes.length === 0) {
    // Fallback while modes are loading or if fetch failed
    return null
  }

  return (
    <div style={{ marginBottom: 12 }}>
      <div
        style={{
          fontSize: 10,
          color: 'var(--muted)',
          textTransform: 'uppercase',
          letterSpacing: '0.05em',
          marginBottom: 6,
        }}
      >
        Mode
      </div>
      <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
        {modes.map(mode => {
          const active = selectedMode === mode.id
          return (
            <button
              key={mode.id}
              data-mode-id={mode.id}
              aria-pressed={active}
              title={mode.description}
              onClick={() => onSelect(mode)}
              style={{
                padding: '4px 12px',
                fontSize: 11,
                borderRadius: 12,
                border: `1px solid ${active ? 'var(--accent)' : 'var(--border)'}`,
                background: active ? 'var(--accent)' : 'transparent',
                color: active ? '#fff' : 'var(--foreground)',
                cursor: 'pointer',
                transition: 'background 0.1s, border-color 0.1s',
                fontWeight: active ? 600 : 400,
              }}
            >
              {mode.label}
            </button>
          )
        })}
      </div>
    </div>
  )
}
