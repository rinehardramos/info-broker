import React, { useState } from 'react'
import { cn } from '@/lib/utils'
import type { BrainSuggestion } from '@/stores/runStreamStore'

type BannerState = 'active' | 'queued' | 'error'

interface BrainSuggestionBannerProps {
  suggestion: BrainSuggestion
  onDismiss: () => void
  onAction: (suggestion: BrainSuggestion) => Promise<void>
}

const ACTION_LABELS: Record<string, string> = {
  aggregate: 'Aggregate & Summarize',
  report: 'Create Report',
  presentation: 'Create Presentation',
  'save-as-pipeline': 'Save as Pipeline',
  'rerun-enriched': 'Use enriched query',
  inject: 'Inject node',
}

export function BrainSuggestionBanner({
  suggestion,
  onDismiss,
  onAction,
}: BrainSuggestionBannerProps) {
  const [state, setState] = useState<BannerState>('active')
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  async function handleAction() {
    setState('queued')
    try {
      await onAction(suggestion)
    } catch (err) {
      setState('error')
      setErrorMsg(err instanceof Error ? err.message : 'Action failed')
    }
  }

  if (state === 'error') {
    return (
      <div
        data-slot="brain-suggestion-banner"
        className="rounded-lg p-3 bg-red-950/40 border border-red-800 animate-in fade-in duration-200"
      >
        <div className="flex items-center gap-2 mb-1">
          <span className="text-sm">⚠</span>
          <span className="text-xs font-semibold text-red-400">
            {suggestion.title} — failed
          </span>
        </div>
        <p className="text-xs text-red-300/80 mb-2">{errorMsg}</p>
        <button
          onClick={() => { setState('active'); setErrorMsg(null) }}
          className="text-xs px-2 py-1 rounded bg-red-900 text-red-300 hover:bg-red-800 transition-colors"
        >
          Retry
        </button>
      </div>
    )
  }

  if (state === 'queued') {
    return (
      <div
        data-slot="brain-suggestion-banner"
        className="rounded-lg p-3 bg-card border border-border opacity-60 animate-in fade-in duration-200"
      >
        <div className="flex items-center gap-2">
          <div className="w-3 h-3 rounded-full border-2 border-border border-t-violet-500 animate-spin" />
          <span className="text-xs text-muted-foreground">
            {suggestion.title} — queued…
          </span>
        </div>
      </div>
    )
  }

  const primaryLabel = suggestion.action
    ? (ACTION_LABELS[suggestion.action] ?? suggestion.action)
    : 'Accept'

  return (
    <div
      data-slot="brain-suggestion-banner"
      className={cn(
        'rounded-lg p-3 bg-gradient-to-br from-violet-950/40 to-background border border-violet-800/60',
        'animate-in fade-in slide-in-from-top-1 duration-300',
      )}
    >
      <div className="flex items-start gap-2.5">
        <div className="w-6 h-6 rounded bg-violet-900/60 flex items-center justify-center flex-shrink-0 mt-0.5 text-sm">
          🧠
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-xs font-semibold text-violet-300 mb-0.5">{suggestion.title}</p>
          {suggestion.body && (
            <p className="text-xs text-muted-foreground leading-relaxed mb-2">
              {suggestion.body}
            </p>
          )}
          <div className="flex gap-2 flex-wrap">
            <button
              onClick={handleAction}
              className="text-xs px-2.5 py-1 rounded bg-violet-700 text-violet-100 hover:bg-violet-600 font-medium transition-colors"
            >
              {primaryLabel}
            </button>
            <button
              onClick={onDismiss}
              className="text-xs px-2.5 py-1 rounded bg-muted text-muted-foreground hover:text-foreground border border-border transition-colors"
            >
              Dismiss
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
