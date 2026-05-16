import React, { useState } from 'react'
import { useRunStreamStore } from '@/stores/runStreamStore'
import { NodeResultCard } from '../results/NodeResultCard'
import { NodeResultDetailModal } from '../results/NodeResultDetailModal'
import { BrainSuggestionBanner } from '../results/BrainSuggestionBanner'
import { CandidateComparison } from '../results/CandidateComparison'
import { brainApi } from '@/api/brain'
import { useChatStore } from '@/stores/chatStore'
import type { NodeCard, BrainSuggestion } from '@/stores/runStreamStore'

const COLLAPSE_THRESHOLD = 30

interface StreamingCardListProps {
  runId: string
  /**
   * When set, only cards whose `phaseId` and `slotIdx` match are shown.
   * Cards that lack this metadata (legacy IS runs) are always shown.
   */
  filterByTactician?: { phaseId: string; slotIdx: number }
}

export function StreamingCardList({ runId, filterByTactician }: StreamingCardListProps) {
  const run = useRunStreamStore((s) => s.runsById[runId])
  const dismissSuggestion = useRunStreamStore((s) => s.dismissSuggestion)
  const appendMsg = useChatStore((s) => s.appendBrainSuggestionAsMessage)

  const [selectedCard, setSelectedCard] = useState<NodeCard | null>(null)
  const [showOlder, setShowOlder] = useState(false)

  if (!run) {
    return (
      <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
        No events yet.
      </div>
    )
  }

  const { cardOrder, cards, suggestions, dismissedSuggestionIds, rankedCandidates = [], achMatrix = null } = run
  const visibleSuggestions = suggestions.filter((s) => !dismissedSuggestionIds.has(s.id))

  // When a tactician filter is active, restrict to cards whose phaseId+slotIdx
  // match.  Cards without this metadata (legacy IS runs) always pass through.
  const filteredOrder = filterByTactician
    ? cardOrder.filter(nodeId => {
        const card = cards[nodeId] as NodeCard & { phaseId?: string; slotIdx?: number }
        if (card?.phaseId == null) return true  // no metadata → include (legacy card)
        return card.phaseId === filterByTactician.phaseId && card.slotIdx === filterByTactician.slotIdx
      })
    : cardOrder

  const olderCount = Math.max(0, filteredOrder.length - COLLAPSE_THRESHOLD)
  const visibleOrder = showOlder
    ? filteredOrder
    : filteredOrder.slice(Math.max(0, filteredOrder.length - COLLAPSE_THRESHOLD))

  async function handleAction(suggestion: BrainSuggestion) {
    if (!suggestion.action) return
    switch (suggestion.action) {
      case 'aggregate': {
        const result = await brainApi.aggregate(runId)
        appendMsg({ id: `agg-${Date.now()}`, title: 'Aggregated Summary', body: result.summary })
        break
      }
      case 'inject': {
        const nodeSpec = suggestion.payload?.nodeSpec as Record<string, unknown> | undefined
        await brainApi.injectNode(runId, { node_spec: nodeSpec })
        dismissSuggestion(runId, suggestion.id)
        break
      }
      case 'save-as-pipeline': {
        const name = (suggestion.payload?.name as string | undefined) ?? 'Saved Pipeline'
        await brainApi.saveAsPipeline(runId, name)
        appendMsg({ id: `save-${Date.now()}`, title: 'Pipeline saved', body: `Saved as "${name}"` })
        break
      }
      default:
        break
    }
  }

  return (
    <div className="flex flex-col gap-2.5 p-4 overflow-y-auto h-full">
      {/* Candidate comparison is injected above the card list when the IS engine
          run finishes with 2+ distinct candidates. Renders nothing otherwise. */}
      {rankedCandidates.length >= 2 && (
        <CandidateComparison candidates={rankedCandidates} achMatrix={achMatrix} />
      )}

      {visibleSuggestions.map((sug) => (
        <BrainSuggestionBanner
          key={sug.id}
          suggestion={sug}
          onDismiss={() => dismissSuggestion(runId, sug.id)}
          onAction={handleAction}
        />
      ))}

      {filterByTactician && (
        <div className="text-[10px] text-violet-400 bg-violet-950/30 border border-violet-800/40 rounded px-2 py-1 text-center">
          Showing cards for Slot {filterByTactician.slotIdx} · {filterByTactician.phaseId.replace(/_/g, ' ')}
          {' '}(click column again to clear)
        </div>
      )}

      {!showOlder && olderCount > 0 && (
        <button
          onClick={() => setShowOlder(true)}
          className="text-xs text-muted-foreground hover:text-foreground text-center py-1 border border-dashed border-border rounded transition-colors"
        >
          Show {olderCount} older results
        </button>
      )}

      {visibleOrder.map((nodeId) => {
        const card = cards[nodeId]
        if (!card) return null
        return (
          <NodeResultCard
            key={nodeId}
            card={card}
            onClick={() => setSelectedCard(card)}
          />
        )
      })}

      {cardOrder.length === 0 && (
        <p className="text-sm text-muted-foreground italic text-center mt-8">
          No node events received yet.
        </p>
      )}

      <NodeResultDetailModal
        card={selectedCard}
        open={!!selectedCard}
        onClose={() => setSelectedCard(null)}
        runId={runId}
      />
    </div>
  )
}
