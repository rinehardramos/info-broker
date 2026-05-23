import React from 'react'

export interface RunBadgeProps {
  runId: string
  className?: string
}

export function RunBadge({ runId, className = '' }: RunBadgeProps) {
  const display = runId ? runId.slice(0, 8) : '-'
  const onClick = async () => {
    if (runId && navigator.clipboard?.writeText) {
      try {
        await navigator.clipboard.writeText(runId)
      } catch {
        // best-effort copy; ignore failure (e.g. no permission)
      }
    }
  }
  return (
    <button
      type="button"
      data-testid="run-badge"
      title={runId || ''}
      onClick={onClick}
      className={`inline-flex items-center gap-1 rounded border border-zinc-300 bg-zinc-100 px-2 py-0.5 font-mono text-xs text-zinc-700 hover:bg-zinc-200 ${className}`}
    >
      <span>run:</span>
      <span>{display}</span>
    </button>
  )
}
