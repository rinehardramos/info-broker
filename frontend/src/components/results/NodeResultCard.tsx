import React from 'react'
import { cn } from '@/lib/utils'
import { formatToolResult } from '@/lib/toolResultFormatter'
import { tryRenderFindings } from './FindingView'
import type { NodeCard } from '@/stores/runStreamStore'
import { SourceClassBadge } from './SourceClassBadge'
import type { SourceClass } from '@/types/research'

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
    const isTerminal = card.status === 'succeeded' || card.status === 'failed'
    // First source URL (if any) is shown as an inline 'link' badge so the user
    // can jump to the source without opening the modal.
    const firstSourceUrl = card.sources?.find((s) => s.url)?.url

    // Try to render as a structured finding (candidate, snippet, confidence,
    // source link). Falls back to formatted text when shape doesn't match.
    const structuredBody = isTerminal
      ? tryRenderFindings(card.output ?? card.preview, { limit: 3, compact: false })
      : null
    const formatted = isTerminal && !structuredBody ? formatToolResult(card.preview) : null
    const displayBody = formatted?.pretty ?? card.preview

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

        {/* Body — render findings as human-readable cards (FindingView) when
            the shape matches; fall back to pretty text only when it doesn't. */}
        {isTerminal && structuredBody ? (
          structuredBody
        ) : (
          <p
            className={cn(
              'text-xs text-foreground/80 leading-relaxed whitespace-pre-wrap',
              !isTerminal && 'line-clamp-3',
              isTerminal && 'line-clamp-4',
            )}
          >
            {displayBody || (isPending ? 'Waiting to run…' : '')}
            {isStreaming && (
              <span className="inline-block w-0.5 h-3 bg-violet-500 animate-pulse ml-0.5 align-text-bottom" />
            )}
          </p>
        )}

        {/* Count derived from items/results/findings array, if present */}
        {isTerminal && formatted?.count != null && (
          <div className="mt-1.5 text-[10px] text-emerald-400/80">
            {formatted.count} {formatted.count === 1 ? 'result' : 'results'}
          </div>
        )}

        {card.sources && card.sources.length > 0 && (
          <div className="flex gap-1.5 mt-2 flex-wrap">
            {card.sources.map((s, i) => {
              // Sources may optionally carry a source_class when emitted by IS engine v2.
              const extendedSource = s as typeof s & { source_class?: SourceClass }
              return (
                <span key={i} className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground">
                  {extendedSource.source_class && (
                    <SourceClassBadge sourceClass={extendedSource.source_class} compact />
                  )}
                  {s.label ?? s.url ?? 'source'}
                </span>
              )
            })}
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

        {/* Finished-card action row: source link + Rate stub. */}
        {isTerminal && (firstSourceUrl || true) && (
          <div className="mt-2 flex items-center gap-2">
            {firstSourceUrl && (
              <a
                href={firstSourceUrl}
                target="_blank"
                rel="noopener noreferrer"
                onClick={(e) => e.stopPropagation()}
                className="text-[10px] text-sky-400 hover:underline"
              >
                link ↗
              </a>
            )}
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation()
                // Rate is wired up in the modal (Admiralty rating row) for
                // findings. Per-tool ratings aren't persisted server-side
                // yet — this button just opens the modal to the Sources tab
                // for now.
                onClick()
              }}
              className="text-[10px] px-2 py-0.5 rounded border border-border text-muted-foreground hover:text-foreground hover:border-violet-500 transition-colors"
            >
              Rate
            </button>
            <span className="ml-auto text-[10px] text-muted-foreground/60 italic">Click for details →</span>
          </div>
        )}
        {!isTerminal && (
          <p className="text-[10px] text-muted-foreground/60 mt-1.5 italic">Click to expand →</p>
        )}
      </div>
    )
  },
  (prev, next) =>
    prev.card.nodeId === next.card.nodeId &&
    prev.card.status === next.card.status &&
    prev.card.preview.length === next.card.preview.length,
)

export { NodeResultCard }
