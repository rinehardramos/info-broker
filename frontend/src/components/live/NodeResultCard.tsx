import React from 'react'
import { cn } from '@/lib/utils'
import type { NodeCard } from '@/stores/runStreamStore'

interface NodeResultCardProps {
  card: NodeCard
  onClick: () => void
}

const STATUS_BORDER: Record<string, string> = {
  succeeded: 'border-l-green-500',
  failed: 'border-l-red-500',
  running: 'border-l-amber-400',
  streaming: 'border-l-amber-400',
  canceled: 'border-l-muted-foreground',
  pending: 'border-l-violet-600',
}

const STATUS_BADGE: Record<string, string> = {
  succeeded: 'bg-green-950 text-green-400',
  failed: 'bg-red-950 text-red-400',
  running: 'bg-amber-950 text-amber-400',
  streaming: 'bg-amber-950 text-yellow-300',
  canceled: 'bg-muted text-muted-foreground',
  pending: 'bg-violet-950 text-violet-400',
}

function elapsedLabel(card: NodeCard): string {
  if (card.finishedAt && card.startedAt) {
    return `${((card.finishedAt - card.startedAt) / 1000).toFixed(1)}s`
  }
  if (card.startedAt) {
    return `${((Date.now() - card.startedAt) / 1000).toFixed(1)}s…`
  }
  return '—'
}

const NodeResultCard = React.memo(
  function NodeResultCard({ card, onClick }: NodeResultCardProps) {
    const borderClass = STATUS_BORDER[card.status] ?? 'border-l-border'
    const badgeClass = STATUS_BADGE[card.status] ?? 'bg-muted text-muted-foreground'
    const isPending = card.status === 'pending'
    const isStreaming = card.status === 'streaming'

    return (
      <div
        data-slot="node-result-card"
        role="button"
        tabIndex={0}
        onClick={onClick}
        onKeyDown={(e) => e.key === 'Enter' && onClick()}
        className={cn(
          'border border-border border-l-2 rounded-lg p-3 cursor-pointer',
          'bg-card hover:border-violet-700 transition-colors',
          'animate-in fade-in slide-in-from-bottom-2 duration-300',
          borderClass,
          isPending && 'border-dashed opacity-70',
        )}
      >
        <div className="flex items-center gap-2 mb-1.5">
          <span className="text-xs font-semibold text-muted-foreground">{card.nodeName}</span>
          <span className={cn('text-[10px] font-semibold px-1.5 py-0.5 rounded-full', badgeClass)}>
            {card.status}
          </span>
          {card.injectedBy && (
            <span className="text-[10px] text-violet-500">↳ injected</span>
          )}
          <span className="ml-auto text-[10px] text-muted-foreground">{elapsedLabel(card)}</span>
        </div>

        <p className="text-xs text-foreground/80 leading-relaxed line-clamp-3">
          {card.preview || (isPending ? 'Waiting to run…' : '')}
          {isStreaming && (
            <span className="inline-block w-0.5 h-3 bg-violet-500 animate-pulse ml-0.5 align-text-bottom" />
          )}
        </p>

        {card.sources && card.sources.length > 0 && (
          <div className="flex gap-1.5 mt-2 flex-wrap">
            {card.sources.map((s, i) => (
              <span key={i} className="text-[10px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground">
                {s.label ?? s.url ?? 'source'}
              </span>
            ))}
          </div>
        )}

        {card.confidence !== undefined && (
          <div className="mt-2 flex items-center gap-1.5">
            <span className="text-[10px] text-muted-foreground">Confidence</span>
            <div className="flex-1 h-1 rounded bg-muted">
              <div
                className="h-1 rounded bg-violet-500"
                style={{ width: `${Math.round(card.confidence * 100)}%` }}
              />
            </div>
            <span className="text-[10px] text-violet-400">{Math.round(card.confidence * 100)}%</span>
          </div>
        )}

        <p className="text-[10px] text-muted-foreground/60 mt-1.5 italic">Click to expand →</p>
      </div>
    )
  },
  (prev, next) =>
    prev.card.nodeId === next.card.nodeId &&
    prev.card.status === next.card.status &&
    prev.card.preview.length === next.card.preview.length,
)

export { NodeResultCard }
