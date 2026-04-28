import { useState, KeyboardEvent } from 'react'

interface Props {
  label: string
  tags: string[]
  onChange: (tags: string[]) => void
  placeholder?: string
}

const pill: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: 4,
  padding: '2px 8px',
  borderRadius: 12,
  background: 'var(--accent, #4f8ef7)',
  color: '#fff',
  fontSize: 12,
}

const inputStyle: React.CSSProperties = {
  flex: 1,
  minWidth: 120,
  background: 'transparent',
  border: 'none',
  outline: 'none',
  color: 'var(--text)',
  fontSize: 14,
}

const containerStyle: React.CSSProperties = {
  display: 'flex',
  flexWrap: 'wrap',
  gap: 6,
  padding: '6px 8px',
  border: '1px solid var(--border)',
  borderRadius: 6,
  background: 'var(--panel)',
  cursor: 'text',
}

export default function TagInput({ label, tags, onChange, placeholder = 'Type and press Enter' }: Props) {
  const [input, setInput] = useState('')

  const addTag = (value: string) => {
    const trimmed = value.trim()
    if (trimmed && !tags.includes(trimmed)) {
      onChange([...tags, trimmed])
    }
    setInput('')
  }

  const removeTag = (index: number) => {
    onChange(tags.filter((_, i) => i !== index))
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault()
      addTag(input)
    } else if (e.key === 'Backspace' && input === '' && tags.length > 0) {
      removeTag(tags.length - 1)
    }
  }

  return (
    <div>
      <label className="text-xs mb-1 block" style={{ color: 'var(--muted)' }}>{label}</label>
      <div style={containerStyle} onClick={(e) => (e.currentTarget.querySelector('input') as HTMLInputElement)?.focus()}>
        {tags.map((tag, i) => (
          <span key={i} style={pill}>
            {tag}
            <button
              type="button"
              onClick={() => removeTag(i)}
              style={{ background: 'none', border: 'none', color: '#fff', cursor: 'pointer', padding: 0, lineHeight: 1 }}
              aria-label={`Remove ${tag}`}
            >
              ×
            </button>
          </span>
        ))}
        <input
          style={inputStyle}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          onBlur={() => input && addTag(input)}
          placeholder={tags.length === 0 ? placeholder : ''}
          aria-label={label}
        />
      </div>
    </div>
  )
}
