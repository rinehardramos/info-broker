import { useState, useRef, type ReactNode } from 'react'
import { ChevronDown, ChevronUp, Play, Loader2 } from 'lucide-react'

interface ActionDrawerProps {
  label: string
  icon: ReactNode
  color: string
  disabled?: boolean
  loading?: boolean
  loadingLabel?: string
  onRun: (context: string) => void
  children?: ReactNode
  placeholder?: string
}

export function ActionDrawer({
  label,
  icon,
  color,
  disabled = false,
  loading = false,
  loadingLabel,
  onRun,
  children,
  placeholder = 'Add context...',
}: ActionDrawerProps) {
  const [open, setOpen] = useState(false)
  const [context, setContext] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  function handleToggleDrawer() {
    const next = !open
    setOpen(next)
    if (next) setTimeout(() => inputRef.current?.focus(), 0)
  }

  function handleRunWithContext() {
    onRun(context)
    setOpen(false)
    setContext('')
  }

  const isDisabled = disabled || loading

  return (
    <div style={{ display: 'inline-flex', flexDirection: 'column', verticalAlign: 'top' }}>
      {/* Split button */}
      <div
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          background: `${color}15`,
          border: `1px solid ${color}40`,
          borderRadius: open ? '8px 8px 0 0' : 8,
          overflow: 'hidden',
          transition: 'all 0.15s ease',
        }}
      >
        {/* Main action */}
        <button
          onClick={() => !isDisabled && onRun('')}
          disabled={isDisabled}
          style={{
            display: 'flex', alignItems: 'center', gap: 6,
            background: 'transparent', border: 'none', color,
            fontSize: 11, fontWeight: 600,
            padding: '7px 12px',
            cursor: isDisabled ? 'not-allowed' : 'pointer',
            opacity: isDisabled ? 0.5 : 1,
            whiteSpace: 'nowrap',
            transition: 'opacity 0.15s',
          }}
        >
          {loading ? <Loader2 size={13} style={{ animation: 'spin 1s linear infinite' }} /> : icon}
          {loading && loadingLabel ? loadingLabel : label}
        </button>

        {/* Divider */}
        <div style={{ width: 1, height: 20, background: `${color}30` }} />

        {/* Chevron */}
        <button
          onClick={handleToggleDrawer}
          disabled={isDisabled}
          title={open ? 'Close options' : 'Add context'}
          style={{
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            background: open ? `${color}15` : 'transparent',
            border: 'none', color,
            padding: '7px 8px',
            cursor: isDisabled ? 'not-allowed' : 'pointer',
            opacity: isDisabled ? 0.5 : 1,
            transition: 'background 0.15s',
          }}
        >
          {open ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
        </button>
      </div>

      {/* Drawer */}
      {open && (
        <div
          style={{
            background: 'var(--panel2)',
            border: `1px solid ${color}30`,
            borderTop: 'none',
            borderRadius: '0 0 8px 8px',
            padding: 10,
            minWidth: 240,
          }}
        >
          <input
            ref={inputRef}
            type="text"
            value={context}
            onChange={e => setContext(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') handleRunWithContext() }}
            placeholder={placeholder}
            style={{
              background: 'var(--bg)', border: '1px solid var(--border)',
              color: 'var(--text)', fontSize: 11,
              padding: '6px 8px', borderRadius: 6,
              width: '100%', boxSizing: 'border-box', outline: 'none',
            }}
          />
          {children}
          <div style={{ marginTop: 8, display: 'flex', justifyContent: 'flex-end' }}>
            <button
              onClick={handleRunWithContext}
              style={{
                display: 'flex', alignItems: 'center', gap: 4,
                background: color, color: '#fff',
                fontSize: 10, fontWeight: 600,
                padding: '5px 12px', borderRadius: 6,
                cursor: 'pointer', border: 'none',
              }}
            >
              <Play size={10} fill="#fff" /> Run
            </button>
          </div>
        </div>
      )}

      <style>{`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}</style>
    </div>
  )
}
