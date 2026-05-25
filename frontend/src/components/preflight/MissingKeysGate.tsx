import { useState } from 'react'
import { storeApiKey } from '../../api/v3'
import type { MissingKeyTool } from '../../hooks/usePreflight'

interface Props {
  /** Tools whose API key is not configured (from the /preflight/confirm gate). */
  missingTools: MissingKeyTool[]
  /** Called after a key is stored so the parent can re-issue confirm and refresh. */
  onKeyStored: () => void
  /** Called when the user chooses to run without configuring the missing keys. */
  onProceedAnyway: () => void
  /** Optional: parent is busy re-issuing confirm / launching. */
  busy?: boolean
}

/**
 * Phase 2 (#75) pre-run missing-key decision gate. Shown in place of starting a
 * run when the chosen strategy needs API keys that aren't configured. Per tool:
 * setup instructions + "Get API key" link + an inline key entry. A global
 * "Proceed anyway" lets the run start without the keys (tools degrade
 * gracefully). Key values are sent once to the encrypted vault and never echoed.
 */
export default function MissingKeysGate({ missingTools, onKeyStored, onProceedAnyway, busy }: Props) {
  return (
    <div
      className="flex flex-col gap-3 p-4 rounded"
      data-testid="missing-keys-gate"
      style={{ background: 'var(--panel, #141414)', border: '1px solid var(--border, #333)' }}
    >
      <div className="flex flex-col gap-1">
        <span className="text-sm font-semibold" style={{ color: 'var(--text)' }}>
          Some tools for this run need an API key
        </span>
        <span className="text-[11px]" style={{ color: 'var(--subtext)' }}>
          Add a key to enable richer results (e.g. per-lead contact enrichment), or proceed without
          them — the affected tools will be skipped and marked unavailable.
        </span>
      </div>

      {missingTools.map((tool) => (
        <MissingKeyCard key={tool.key_name} tool={tool} onStored={onKeyStored} />
      ))}

      <div className="flex items-center justify-end gap-3 pt-1">
        <button
          onClick={onProceedAnyway}
          disabled={busy}
          data-testid="missing-keys-proceed-anyway"
          className="text-xs px-3 py-1.5 rounded"
          style={{
            background: 'var(--panel)',
            color: 'var(--text)',
            border: '1px solid var(--border)',
            cursor: busy ? 'not-allowed' : 'pointer',
            opacity: busy ? 0.6 : 1,
          }}
        >
          Proceed anyway
        </button>
      </div>
    </div>
  )
}

function MissingKeyCard({ tool, onStored }: { tool: MissingKeyTool; onStored: () => void }) {
  const [value, setValue] = useState('')
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const save = async () => {
    if (!value.trim()) return
    setSaving(true)
    setError(null)
    try {
      await storeApiKey(tool.key_name, value.trim(), 'user')
      setSaved(true)
      setValue('')
      onStored()
    } catch {
      setError('Failed to save key. Check the value and try again.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div
      className="flex flex-col gap-2 p-3 rounded"
      data-testid={`missing-key-card-${tool.key_name}`}
      style={{ background: 'var(--bg, #0f0f0f)', border: '1px solid var(--border, #333)' }}
    >
      <span className="text-xs font-medium" style={{ color: 'var(--text)' }}>
        {tool.display_name}
      </span>
      <p className="text-[11px]" style={{ color: 'var(--subtext)' }}>
        Requires API key: <code style={{ color: 'var(--text)' }}>{tool.key_name}</code>
      </p>
      {tool.setup_instructions && (
        <p className="text-[11px]" style={{ color: 'var(--subtext)', lineHeight: 1.5 }}>
          {tool.setup_instructions}
        </p>
      )}

      <div className="flex items-center gap-2 flex-wrap">
        {tool.setup_url && (
          <a
            href={tool.setup_url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-[11px]"
            data-testid={`missing-key-setup-url-${tool.key_name}`}
            style={{ color: 'var(--accent)' }}
          >
            Get API key →
          </a>
        )}
      </div>

      {saved ? (
        <span className="text-[11px]" style={{ color: '#34d399' }} data-testid={`missing-key-saved-${tool.key_name}`}>
          ✓ Key saved
        </span>
      ) : (
        <div className="flex items-center gap-2">
          <input
            type="password"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder={`Paste ${tool.key_name}`}
            data-testid={`missing-key-input-${tool.key_name}`}
            autoComplete="off"
            className="flex-1 text-[11px] px-2 py-1 rounded"
            style={{ background: 'var(--panel)', color: 'var(--text)', border: '1px solid var(--border)' }}
          />
          <button
            onClick={save}
            disabled={saving || !value.trim()}
            data-testid={`missing-key-save-${tool.key_name}`}
            className="text-[11px] px-3 py-1 rounded"
            style={{
              background: 'var(--accent, #2563eb)',
              color: '#fff',
              border: 'none',
              cursor: saving || !value.trim() ? 'not-allowed' : 'pointer',
              opacity: saving || !value.trim() ? 0.6 : 1,
            }}
          >
            {saving ? 'Saving…' : 'Save key'}
          </button>
        </div>
      )}
      {error && (
        <span className="text-[11px]" style={{ color: '#f87171' }}>
          {error}
        </span>
      )}
    </div>
  )
}
