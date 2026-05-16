/**
 * DialPicker — segmented control for a single budget dial.
 *
 * Props:
 *   dial           — identifies which dial ("speed"|"capability"|"resource"|"depth"|"hypothesis_count")
 *   value          — currently selected level
 *   levels         — ordered list of allowed levels for this dial
 *   onChange       — called with the newly selected level
 *   disabledLevels — set of levels that are greyed out (strategy minimums enforcement)
 *   disabledTooltip — tooltip shown when hovering a disabled level
 *   label          — human-readable dial name shown above the control
 */

export type DialName =
  | 'speed'
  | 'capability'
  | 'resource'
  | 'depth'
  | 'hypothesis_count'

interface DialPickerProps {
  dial: DialName
  value: string
  levels: readonly string[]
  onChange: (value: string) => void
  disabledLevels?: Set<string>
  disabledTooltip?: string
  label?: string
}

export function DialPicker({
  dial: _dial,
  value,
  levels,
  onChange,
  disabledLevels,
  disabledTooltip,
  label,
}: DialPickerProps) {
  return (
    <div style={{ marginBottom: 8 }}>
      {label && (
        <div
          style={{
            fontSize: 10,
            color: 'var(--muted)',
            textTransform: 'uppercase',
            letterSpacing: '0.05em',
            marginBottom: 4,
          }}
        >
          {label}
        </div>
      )}
      <div style={{ display: 'flex', gap: 2, flexWrap: 'wrap' }}>
        {levels.map(level => {
          const disabled = disabledLevels?.has(level) ?? false
          const active = value === level
          return (
            <button
              key={level}
              disabled={disabled}
              title={
                disabled
                  ? (disabledTooltip ?? `'${level}' is below the minimum required for this strategy`)
                  : undefined
              }
              onClick={() => {
                if (!disabled) onChange(level)
              }}
              style={{
                padding: '3px 9px',
                fontSize: 11,
                borderRadius: 4,
                border: `1px solid ${active ? 'var(--accent)' : 'var(--border)'}`,
                background: active ? 'var(--accent)' : 'transparent',
                color: disabled
                  ? 'var(--muted)'
                  : active
                  ? '#fff'
                  : 'var(--foreground)',
                cursor: disabled ? 'not-allowed' : 'pointer',
                opacity: disabled ? 0.4 : 1,
                transition: 'background 0.1s, border-color 0.1s',
              }}
            >
              {level}
            </button>
          )
        })}
      </div>
    </div>
  )
}
