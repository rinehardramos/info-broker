import React from 'react'
import type { NodeCard } from '@/stores/runStreamStore'
import { SourceClassBadge } from './SourceClassBadge'
import type { SourceClass } from '@/types/research'

interface HypothesisTabProps {
  card: NodeCard
}

/**
 * HypothesisTab — new tab in NodeResultDetailModal.
 *
 * Shows the IS brain hypothesis context for this card's slot:
 * - Which hypothesis slot this card belongs to (card.branchId encodes the slot)
 * - The PIR / hypothesis being tested (card.pir)
 * - Confirm or disconfirm status
 * - Findings produced by this slot (from card.output when it carries IS findings)
 * - Forbidden candidates (if encoded in output)
 *
 * This is purely presentational — all data lives in the NodeCard that the
 * WebSocket events populate. No new API calls.
 */
export function HypothesisTab({ card }: HypothesisTabProps) {
  // Hypothesis label from PIR or branchId
  const hypothesis = card.pir ?? null
  const slotIdx = card.branchId ?? null

  // Try to pull IS findings from card.output when the backend serialises them
  const output = card.output as Record<string, unknown> | null | undefined
  const rawFindings: unknown[] = Array.isArray(output?.findings)
    ? (output!.findings as unknown[])
    : []

  // Forbidden candidates may be encoded in output
  const forbidden: string[] = Array.isArray(output?.forbidden_candidates)
    ? (output!.forbidden_candidates as string[])
    : []

  // Tactic used
  const tacticUsed =
    typeof output?.tactic_used === 'string' ? output.tactic_used : null

  // Simple confirm/disconfirm derivation from confidence
  const confidence = card.confidence
  const hasConfirm =
    confidence !== undefined ? confidence >= 0.5 : null

  return (
    <div className="space-y-4 text-sm">
      {/* Slot + tactic */}
      <div className="grid grid-cols-[120px_1fr] gap-y-1.5 gap-x-3">
        {slotIdx !== null && (
          <>
            <dt className="text-muted-foreground text-xs">Hypothesis slot</dt>
            <dd className="text-foreground/90 font-mono text-xs">{slotIdx}</dd>
          </>
        )}
        {tacticUsed && (
          <>
            <dt className="text-muted-foreground text-xs">Tactic used</dt>
            <dd className="text-foreground/90 font-mono text-xs">{tacticUsed}</dd>
          </>
        )}
        {hasConfirm !== null && (
          <>
            <dt className="text-muted-foreground text-xs">Status</dt>
            <dd>
              <span
                className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${
                  hasConfirm
                    ? 'bg-emerald-950 text-emerald-400'
                    : 'bg-red-950 text-red-400'
                }`}
              >
                {hasConfirm ? 'Confirms hypothesis' : 'Disconfirms hypothesis'}
              </span>
            </dd>
          </>
        )}
      </div>

      {/* Hypothesis being tested */}
      {hypothesis && (
        <div>
          <p className="text-[10px] text-amber-400 uppercase font-semibold mb-1">
            Hypothesis / PIR
          </p>
          <p className="text-foreground/80 text-xs leading-relaxed bg-muted/20 rounded px-2 py-1.5">
            {hypothesis}
          </p>
        </div>
      )}

      {/* Forbidden candidates */}
      {forbidden.length > 0 && (
        <div>
          <p className="text-[10px] text-muted-foreground uppercase font-semibold mb-1">
            Forbidden candidates (this slot excluded these)
          </p>
          <div className="flex flex-wrap gap-1.5">
            {forbidden.map((c, i) => (
              <span
                key={i}
                className="text-[10px] px-2 py-0.5 rounded bg-red-950/40 border border-red-900/40 text-red-300"
              >
                {c}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Findings from this slot */}
      {rawFindings.length > 0 ? (
        <div>
          <p className="text-[10px] text-muted-foreground uppercase font-semibold mb-2">
            Findings from this slot ({rawFindings.length})
          </p>
          <div className="space-y-2">
            {rawFindings.map((f, i) => {
              const finding = f as Record<string, unknown>
              const sourceClass = (finding.source_class as SourceClass | undefined) ?? 'training_knowledge'
              const snippet =
                typeof finding.evidence_snippet === 'string'
                  ? finding.evidence_snippet
                  : typeof finding.snippet === 'string'
                  ? finding.snippet
                  : ''
              const url =
                typeof finding.source_url === 'string' ? finding.source_url : undefined
              const isDisconfirm = !!finding.is_disconfirm

              return (
                <div
                  key={i}
                  className={`flex items-start gap-2 rounded px-2 py-1.5 border ${
                    isDisconfirm
                      ? 'bg-red-950/20 border-red-900/30'
                      : 'bg-muted/10 border-border/50'
                  }`}
                >
                  <SourceClassBadge sourceClass={sourceClass} compact />
                  <div className="flex-1 min-w-0">
                    {isDisconfirm && (
                      <span className="text-[9px] text-red-400 font-semibold mr-1">DISCONFIRM</span>
                    )}
                    <p className="text-[10px] text-foreground/80 leading-relaxed">
                      {snippet || 'No snippet recorded.'}
                    </p>
                    {url && (
                      <a
                        href={url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-[9px] text-sky-400 hover:underline truncate block mt-0.5"
                      >
                        {url}
                      </a>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      ) : (
        !hypothesis && !slotIdx && !tacticUsed && (
          <p className="text-xs text-muted-foreground italic">
            No hypothesis data available for this card. Hypothesis context is populated for IS
            engine v2 runs.
          </p>
        )
      )}
    </div>
  )
}
