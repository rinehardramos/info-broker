import React, { useState } from 'react'
import type { RankedCandidate, ACHMatrix as ACHMatrixType } from '@/types/research'
import { CandidateRow } from './CandidateRow'
import { ACHMatrix } from './ACHMatrix'

interface CandidateComparisonProps {
  candidates: RankedCandidate[]
  achMatrix?: ACHMatrixType | null
  /** Original user query — used to enrich entity profiles in the evidence modal. */
  context?: string
}

/**
 * Renders a ranked comparison of candidates when two or more exist.
 *
 * Design constraint (UI plan §1 principle 3): the top candidate is highlighted
 * but NOT visually dominant. Runner-ups must read as legitimate alternatives
 * because the #89 failure mode was UIs that hid alternatives.
 */
export function CandidateComparison({ candidates, achMatrix, context }: CandidateComparisonProps) {
  const [showAch, setShowAch] = useState(false)

  if (candidates.length < 2) return null

  // Sort by confidence descending; backend should already send in order, but
  // be defensive since the store just stores whatever the event payload has.
  const sorted = [...candidates].sort((a, b) => b.confidence - a.confidence)

  return (
    <div className="rounded-xl border border-border bg-card/60 p-4 space-y-3">
      {/* Header */}
      <div>
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold text-foreground/90">Candidate Comparison</span>
          <span className="text-[10px] text-muted-foreground">
            {sorted.length} candidates considered
          </span>
        </div>
        <p className="text-[10px] text-muted-foreground mt-0.5">
          All candidates explored independently — expand any row for disconfirm evidence.
        </p>
      </div>

      {/* Column header row */}
      <div className="grid grid-cols-[1fr_90px_32px_32px_32px_32px_80px] items-center gap-2 px-3 text-[9px] font-semibold text-muted-foreground uppercase tracking-wider">
        <span>Candidate</span>
        <span>Confidence</span>
        <span className="text-center" title="Primary signal match">Pri</span>
        <span className="text-center" title="Supporting signal match">Sup</span>
        <span className="text-center" title="Medium type match">Med</span>
        <span className="text-center" title="Recency match">Rec</span>
        <span>Evidence</span>
      </div>

      {/* Candidate rows */}
      <div className="space-y-2">
        {sorted.map((candidate, idx) => (
          <CandidateRow
            key={candidate.name}
            candidate={candidate}
            isTop={idx === 0}
            rank={idx + 1}
            context={context}
          />
        ))}
      </div>

      <p className="text-[9px] text-muted-foreground/60 italic pt-1">
        Pri = primary signal · Sup = supporting signal · Med = medium type · Rec = recency
      </p>

      {/* ACH Matrix expandable section — only shown when matrix is present (P5) */}
      {achMatrix != null && (
        <div className="pt-1 border-t border-border/50">
          <button
            type="button"
            onClick={() => setShowAch((v) => !v)}
            className="flex items-center gap-1.5 text-[10px] text-muted-foreground hover:text-foreground transition-colors"
            aria-expanded={showAch}
          >
            <span className="text-[9px]">{showAch ? '▾' : '▸'}</span>
            <span className="font-medium">
              {showAch ? 'Hide' : 'Show'} ACH Matrix
            </span>
            <span className="text-muted-foreground/60">
              · Heuer Analysis of Competing Hypotheses
            </span>
          </button>
          {showAch && (
            <div className="mt-2">
              <ACHMatrix matrix={achMatrix} />
            </div>
          )}
        </div>
      )}
    </div>
  )
}
