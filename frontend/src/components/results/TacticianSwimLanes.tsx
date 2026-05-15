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

import React, { useState } from 'react'
import type { TacticianState, PhaseState } from '@/types/research'

interface TacticianSwimLanesProps {
  phaseId: string
  tacticians: Record<number, TacticianState>
  phaseStatus: PhaseState['status']
  selectedSlotIdx?: number | null
  onSelectTactician?: (slotIdx: number | null) => void
}

function LockIcon() {
  return (
    <svg
      width="10" height="10" viewBox="0 0 16 16" fill="none"
      aria-hidden="true"
      className="opacity-40 flex-shrink-0"
    >
      <rect x="3" y="7" width="10" height="8" rx="2" fill="currentColor" />
      <path d="M5 7V5a3 3 0 016 0v2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" fill="none" />
    </svg>
  )
}

function TacticianColumn({
  slotIdx,
  state,
  isComplete,
  isSelected,
  onClick,
}: {
  slotIdx: number
  state: TacticianState
  isComplete: boolean
  isSelected: boolean
  onClick: () => void
}) {
  const [forbidExpanded, setForbidExpanded] = useState(false)

  const hasForbidden = state.forbidden_candidates.length > 0
  const hasCandidates = state.candidate_names.length > 0

  return (
    <button
      type="button"
      onClick={onClick}
      className={[
        'flex flex-col gap-1.5 p-2.5 rounded-lg border text-left transition-all cursor-pointer flex-shrink-0 min-w-[160px] max-w-[220px] w-full',
        isSelected
          ? 'border-violet-500 bg-violet-950/30 ring-1 ring-violet-500/50'
          : isComplete
            ? 'border-slate-700 bg-slate-800/30'
            : 'border-slate-700/60 bg-slate-800/20 hover:border-slate-600',
      ].join(' ')}
      aria-pressed={isSelected}
      aria-label={`Tactician slot ${slotIdx}${state.tactic_id ? `, tactic ${state.tactic_id}` : ''}`}
    >
      {/* Header */}
      <div className="flex items-center gap-1.5 justify-between">
        <div className="flex items-center gap-1">
          <span className="text-[10px] font-bold text-slate-400">Slot {slotIdx}</span>
          {state.tactic_id && (
            <span className="text-[10px] text-slate-500 truncate max-w-[100px]" title={state.tactic_id}>
              · {state.tactic_id.replace(/_/g, ' ')}
            </span>
          )}
        </div>
        <LockIcon />
      </div>

      {/* Forbidden candidates (collapsed by default) */}
      {hasForbidden && (
        <div>
          <button
            type="button"
            className="text-[9px] text-rose-400/70 hover:text-rose-400 transition-colors"
            onClick={(e) => { e.stopPropagation(); setForbidExpanded(v => !v) }}
          >
            {forbidExpanded ? '▾' : '▸'} {state.forbidden_candidates.length} forbidden
          </button>
          {forbidExpanded && (
            <ul className="mt-0.5 space-y-0.5">
              {state.forbidden_candidates.map((name, i) => (
                <li key={i} className="text-[9px] text-rose-300/70 pl-1 truncate">✗ {name}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* Live candidate names */}
      {hasCandidates ? (
        <div className="space-y-0.5">
          {state.candidate_names.map((name, i) => (
            <div key={i} className="text-[10px] text-emerald-300 truncate font-medium" title={name}>
              {name}
            </div>
          ))}
        </div>
      ) : (
        <div className="text-[10px] text-slate-600 italic">
          {isComplete ? 'no candidates' : 'searching...'}
        </div>
      )}

      {/* Stats footer */}
      <div className="flex items-center gap-2 mt-auto pt-1 border-t border-slate-700/40">
        {state.findings_count > 0 && (
          <span className="text-[9px] text-slate-500">{state.findings_count} finding{state.findings_count !== 1 ? 's' : ''}</span>
        )}
        {!isComplete && (
          <span className="ml-auto w-1 h-1 rounded-full bg-violet-400 animate-pulse flex-shrink-0" />
        )}
      </div>
    </button>
  )
}

export function TacticianSwimLanes({
  phaseId,
  tacticians,
  phaseStatus,
  selectedSlotIdx,
  onSelectTactician,
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

  return (
    <div className="flex flex-col gap-1.5 px-3 pb-2">
      <div className="flex items-center gap-1 mb-1">
        <span className="text-[10px] font-semibold text-slate-500 uppercase tracking-wide">
          {phaseId.replace(/_/g, ' ')}
        </span>
        <span className="text-[10px] text-slate-600">— {slots.length} parallel tactician{slots.length !== 1 ? 's' : ''}</span>
        <span className="ml-1 text-[9px] text-slate-600 opacity-60" title="Tacticians cannot see each other's findings">
          (isolated)
        </span>
      </div>
      <div className="flex gap-2 overflow-x-auto pb-1">
        {slots.map(({ slotIdx, state }) => (
          <TacticianColumn
            key={slotIdx}
            slotIdx={slotIdx}
            state={state}
            isComplete={isComplete}
            isSelected={selectedSlotIdx === slotIdx}
            onClick={() => onSelectTactician?.(selectedSlotIdx === slotIdx ? null : slotIdx)}
          />
        ))}
      </div>
      {isComplete && (
        <div className="text-[10px] text-slate-600 italic text-center pt-1">
          Phase complete
        </div>
      )}
    </div>
  )
}
