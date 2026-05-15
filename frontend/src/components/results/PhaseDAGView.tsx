/**
 * PhaseDAGView — top-level layout for the v2 three-tier live view.
 *
 * Renders:
 *   1. PhaseProgress strip at top (always visible)
 *   2. TacticianSwimLanes scoped to the active phase
 *   3. A "Compact view" toggle that falls back to the legacy linear ResearchFlow
 *
 * The compact preference is persisted in localStorage under the key
 * "v2_live_view_compact" so it survives page reloads.
 */

import React, { useState, useEffect } from 'react'
import { useRunStreamStore } from '@/stores/runStreamStore'
import { PhaseProgress } from './PhaseProgress'
import { TacticianSwimLanes } from './TacticianSwimLanes'
import { ResearchFlow } from './ResearchFlow'

const COMPACT_STORAGE_KEY = 'v2_live_view_compact'

// Default phase order for media_identification strategy (MVP).
// When more strategies land, the strategist can emit this via the phase_start events.
const DEFAULT_PHASE_ORDER = ['signal_extraction', 'broaden', 'red_team', 'rank_verify']

interface PhaseDAGViewProps {
  runId: string
  /** Optional override of the phase order (e.g. from strategy metadata). */
  phaseOrder?: string[]
  /** Callback when a tactician column is selected so the card list can filter. */
  onSelectTactician?: (filter: { phaseId: string; slotIdx: number } | null) => void
}

function readCompactPref(): boolean {
  try {
    return localStorage.getItem(COMPACT_STORAGE_KEY) === 'true'
  } catch {
    return false
  }
}

function writeCompactPref(value: boolean) {
  try {
    localStorage.setItem(COMPACT_STORAGE_KEY, value ? 'true' : 'false')
  } catch {
    // ignore storage errors
  }
}

export function PhaseDAGView({ runId, phaseOrder, onSelectTactician }: PhaseDAGViewProps) {
  const [compact, setCompact] = useState<boolean>(readCompactPref)
  const [selectedTactician, setSelectedTactician] = useState<{ phaseId: string; slotIdx: number } | null>(null)

  const run = useRunStreamStore(s => s.runsById[runId])
  const phases = run?.phases ?? {}
  const tacticians = run?.tacticians ?? {}
  const activePhase = run?.activePhase ?? null

  // Determine display phase order: use provided override, or fall back to
  // the order inferred from keys in phases (arrival order), or the default.
  const derivedOrder = (() => {
    if (phaseOrder && phaseOrder.length > 0) return phaseOrder
    const knownKeys = Object.keys(phases)
    if (knownKeys.length > 0) {
      // Sort by index in DEFAULT_PHASE_ORDER; unknowns appended at end
      return DEFAULT_PHASE_ORDER.concat(knownKeys.filter(k => !DEFAULT_PHASE_ORDER.includes(k)))
    }
    return DEFAULT_PHASE_ORDER
  })()

  // The swim lanes show the active phase if running, or the last completed phase.
  const displayPhaseId = activePhase ?? (() => {
    const last = derivedOrder.slice().reverse().find(id => phases[id]?.status !== 'pending' && phases[id] != null)
    return last ?? null
  })()

  function handleToggleCompact() {
    setCompact(v => {
      const next = !v
      writeCompactPref(next)
      return next
    })
  }

  function handleSelectTactician(slotIdx: number | null) {
    if (!displayPhaseId) return
    if (slotIdx == null) {
      setSelectedTactician(null)
      onSelectTactician?.(null)
    } else {
      const filter = { phaseId: displayPhaseId, slotIdx }
      setSelectedTactician(filter)
      onSelectTactician?.(filter)
    }
  }

  // Clear selection when phase changes
  useEffect(() => {
    setSelectedTactician(null)
    onSelectTactician?.(null)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activePhase])

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Toolbar */}
      <div className="flex items-center justify-between px-3 py-1 border-b border-slate-800 bg-slate-900/30 flex-shrink-0">
        <span className="text-[10px] font-semibold text-slate-500 uppercase tracking-wide">
          v2 live view
        </span>
        <button
          type="button"
          onClick={handleToggleCompact}
          className="text-[10px] text-slate-500 hover:text-slate-300 transition-colors select-none"
          title={compact ? 'Switch to phase DAG view' : 'Switch to compact legacy view'}
        >
          {compact ? 'DAG view' : 'Compact view'}
        </button>
      </div>

      {compact ? (
        /* Compact fallback — legacy linear flow */
        <div className="flex-1 overflow-hidden">
          <ResearchFlow runId={runId} compact />
        </div>
      ) : (
        /* Full DAG view */
        <div className="flex flex-col flex-1 overflow-hidden">
          {/* Phase strip */}
          <PhaseProgress
            phases={phases}
            activePhase={activePhase}
            phaseOrder={derivedOrder}
          />

          {/* Swim lanes for active / most-recent phase */}
          <div className="flex-1 overflow-y-auto">
            {displayPhaseId != null ? (
              <TacticianSwimLanes
                phaseId={displayPhaseId}
                tacticians={tacticians[displayPhaseId] ?? {}}
                phaseStatus={phases[displayPhaseId]?.status ?? 'pending'}
                selectedSlotIdx={selectedTactician?.phaseId === displayPhaseId ? selectedTactician.slotIdx : null}
                onSelectTactician={handleSelectTactician}
              />
            ) : (
              <div className="flex items-center justify-center h-full text-[11px] text-slate-600 italic px-4 text-center">
                Run started — waiting for first phase...
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
