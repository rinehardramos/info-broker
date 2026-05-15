/**
 * SaveTemplateDialog — Enhancement 3.2
 *
 * Modal for naming a new saved template. Validates uniqueness against existing
 * template names. On confirm, calls onSave(name).
 */
import { useState, useEffect, useRef } from 'react'

interface SaveTemplateDialogProps {
  existingNames: string[]
  onSave: (name: string) => Promise<void>
  onClose: () => void
}

export function SaveTemplateDialog({ existingNames, onSave, onClose }: SaveTemplateDialogProps) {
  const [name, setName] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  const isDuplicate = existingNames.includes(name.trim())
  const isBlank = name.trim().length === 0

  async function handleSave() {
    if (isBlank || saving) return
    if (isDuplicate) {
      setError(`"${name.trim()}" already exists — saving will overwrite it.`)
    }
    setSaving(true)
    setError(null)
    try {
      await onSave(name.trim())
      onClose()
    } catch {
      setError('Failed to save template. Please try again.')
    } finally {
      setSaving(false)
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter') handleSave()
    if (e.key === 'Escape') onClose()
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="save-template-title"
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0,0,0,0.5)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1000,
      }}
      onClick={onClose}
    >
      <div
        style={{
          background: 'var(--background)',
          border: '1px solid var(--border)',
          borderRadius: 8,
          padding: 24,
          maxWidth: 360,
          width: '90%',
        }}
        onClick={e => e.stopPropagation()}
      >
        <h3
          id="save-template-title"
          style={{ marginTop: 0, marginBottom: 12, fontSize: 14, fontWeight: 600 }}
        >
          Save as Template
        </h3>

        <label style={{ fontSize: 12, color: 'var(--muted)', display: 'block', marginBottom: 6 }}>
          Template name
        </label>
        <input
          ref={inputRef}
          type="text"
          value={name}
          onChange={e => {
            setName(e.target.value)
            setError(null)
          }}
          onKeyDown={handleKeyDown}
          maxLength={80}
          placeholder="e.g. Standard media investigation"
          style={{
            width: '100%',
            padding: '6px 10px',
            fontSize: 12,
            border: `1px solid ${isDuplicate ? '#e5a300' : 'var(--border)'}`,
            borderRadius: 4,
            background: 'var(--background)',
            color: 'var(--foreground)',
            boxSizing: 'border-box',
          }}
        />

        {isDuplicate && (
          <div style={{ marginTop: 6, fontSize: 11, color: '#e5a300' }}>
            A template with this name already exists. Saving will overwrite it.
          </div>
        )}

        {error && !isDuplicate && (
          <div style={{ marginTop: 6, fontSize: 11, color: '#c00' }}>{error}</div>
        )}

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 16 }}>
          <button
            onClick={onClose}
            style={{
              padding: '4px 14px',
              fontSize: 12,
              borderRadius: 4,
              border: '1px solid var(--border)',
              background: 'transparent',
              color: 'var(--foreground)',
              cursor: 'pointer',
            }}
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={isBlank || saving}
            style={{
              padding: '4px 14px',
              fontSize: 12,
              borderRadius: 4,
              border: 'none',
              background: 'var(--accent)',
              color: '#fff',
              cursor: isBlank || saving ? 'not-allowed' : 'pointer',
              opacity: isBlank || saving ? 0.6 : 1,
            }}
          >
            {saving ? 'Saving…' : isDuplicate ? 'Overwrite' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  )
}
