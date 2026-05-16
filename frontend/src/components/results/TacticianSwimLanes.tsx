/**
 * TacticianSwimLanes — N side-by-side columns, one per tactician in the active phase.
 *
 * Each column shows:
 *   - Header: "Slot {n} · {tactic_id}" + a subtle lock icon (isolation indicator)
 *   - Forbidden candidates list (collapsed by default, expandable inline)
 *   - Live candidate names as they arrive
 *   - Specialist call count (derived from findings_count as a proxy in MVP)
 *
 * When a phase completes, columns settle into final state.
 * When clicked, calls onSelectTactician so StreamingCardList can filter by slot.
 */

import type { TacticianState, PhaseState } from '@/types/research'

interface TacticianSwimLanesProps {
  phaseId: string
  tacticians: Record<number, TacticianState>
  phaseStatus: PhaseState['status']
  selectedSlotIdx?: number | null
  onSelectTactician?: (slotIdx: number | null) => void
}

export function TacticianSwimLanes({
  phaseId,
  tacticians,
  phaseStatus,
}: TacticianSwimLanesProps) {
  const slots = Object.entries(tacticians).map(([k, v]) => ({ slotIdx: parseInt(k, 10), state: v }))
  slots.sort((a, b) => a.slotIdx - b.slotIdx)

  const isComplete = phaseStatus === 'passed' || phaseStatus === 'failed' || phaseStatus === 'ask_user' || phaseStatus === 'skipped'

  if (slots.length === 0) {
    // Phase has no slot data — for analysis-only tactics (signal_extraction,
    // rank_verify) this is expected: the brain reasons without spawning per-
    // slot work. Show a completion marker instead of an indefinite "waiting".
    if (isComplete) {
      const label = phaseId.replace(/_/g, ' ')
      const statusLabel =
        phaseStatus === 'passed' ? '✓ complete' :
        phaseStatus === 'failed' ? '✗ failed' :
        phaseStatus === 'ask_user' ? '⚠ awaiting input' :
        '· skipped'
      return (
        <div className="px-3 py-3 text-[11px] text-slate-500 italic text-center">
          <span className="font-medium">{label}</span> {statusLabel} —
          analysis phase, no parallel tacticians
        </div>
      )
    }
    return (
      <div className="px-3 py-4 text-[11px] text-slate-600 italic text-center">
        Waiting for tacticians in phase: {phaseId.replace(/_/g, ' ')}
      </div>
    )
  }

  // Compact subtitle row instead of full swim-lane columns. The columns were
  // exposing internal Heuer-tradecraft mechanics (Slot 0/1/2 isolation) that
  // users don't care about — they want findings, not slot-tracking. We
  // surface only: phase name, parallel count, total candidates so far, and
  // a tiny pulse while the phase is still running.
  const totalFindings = slots.reduce((n, s) => n + (s.state.findings_count ?? 0), 0)
  const totalCandidates = slots.reduce((n, s) => n + (s.state.candidate_names?.length ?? 0), 0)
  const totalForbidden = slots.reduce((n, s) => n + (s.state.forbidden_candidates?.length ?? 0), 0)

  return (
    <div className="px-3 py-2 flex items-center gap-2 text-[11px] text-muted-foreground border-b border-border/40">
      <span className="font-semibold text-foreground/80 uppercase tracking-wide text-[10px]">
        {phaseId.replace(/_/g, ' ')}
      </span>
      <span>·</span>
      <span>
        searching {slots.length} hypothes{slots.length !== 1 ? 'es' : 'is'} in parallel
      </span>
      {totalCandidates > 0 && (
        <>
          <span>·</span>
          <span className="text-emerald-400/90">{totalCandidates} candidate{totalCandidates !== 1 ? 's' : ''}</span>
        </>
      )}
      {totalFindings > 0 && (
        <>
          <span>·</span>
          <span>{totalFindings} finding{totalFindings !== 1 ? 's' : ''}</span>
        </>
      )}
      {totalForbidden > 0 && (
        <>
          <span>·</span>
          <span className="text-rose-400/70">{totalForbidden} forbidden</span>
        </>
      )}
      {!isComplete && (
        <span className="ml-auto w-1.5 h-1.5 rounded-full bg-violet-400 animate-pulse flex-shrink-0" />
      )}
      {isComplete && (
        <span className="ml-auto text-emerald-500/80 text-[10px]">✓</span>
      )}
    </div>
  )
}
