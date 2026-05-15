/**
 * PhaseDAGView — top-level layout for the v2 three-tier live view.
 *
 * Renders:
 *   1. PhaseProgress strip at top (always visible)
 *   2. TacticianSwimLanes scoped to the active phase
 *   3. A view-mode toggle: "Live" | "Compact" | "DAG"
 *
 * View mode is persisted in localStorage under VIEW_MODE_STORAGE_KEY.
 * Previously stored boolean "true"/"false" values are migrated transparently:
 *   "true"  → "compact"
 *   "false" → "live"
 */

import React, { useState, useEffect } from 'react'
import { useRunStreamStore } from '@/stores/runStreamStore'
import { PhaseProgress } from './PhaseProgress'
import { TacticianSwimLanes } from './TacticianSwimLanes'
import { ResearchFlow } from './ResearchFlow'
import { InvestigationDAG } from './InvestigationDAG'

export type ViewMode = 'live' | 'compact' | 'dag'

/** Storage key — replaces the old "v2_live_view_compact" boolean key. */
export const VIEW_MODE_STORAGE_KEY = 'v2_live_view_mode'

const DEFAULT_PHASE_ORDER = ['signal_extraction', 'broaden', 'red_team', 'rank_verify']

interface PhaseDAGViewProps {
  runId: string
  phaseOrder?: string[]
  onSelectTactician?: (filter: { phaseId: string; slotIdx: number } | null) => void
}

function readViewMode(): ViewMode {
  try {
    const raw = localStorage.getItem(VIEW_MODE_STORAGE_KEY)
    if (raw === 'live' || raw === 'compact' || raw === 'dag') return raw
    // Migrate old boolean key
    const legacy = localStorage.getItem('v2_live_view_compact')
    if (legacy === 'true') return 'compact'
  } catch {
    // ignore storage errors
  }
  return 'live'
}

function writeViewMode(mode: ViewMode) {
  try {
    localStorage.setItem(VIEW_MODE_STORAGE_KEY, mode)
  } catch {
    // ignore storage errors
  }
}

export function PhaseDAGView({ runId, phaseOrder, onSelectTactician }: PhaseDAGViewProps) {
  const [viewMode, setViewMode] = useState<ViewMode>(readViewMode)
  const [selectedTactician, setSelectedTactician] = useState<{ phaseId: string; slotIdx: number } | null>(null)

  const run = useRunStreamStore(s => s.runsById[runId])
  const phases = run?.phases ?? {}
  const tacticians = run?.tacticians ?? {}
  const activePhase = run?.activePhase ?? null

  const derivedOrder = (() => {
    if (phaseOrder && phaseOrder.length > 0) return phaseOrder
    const knownKeys = Object.keys(phases)
    if (knownKeys.length > 0) {
      return DEFAULT_PHASE_ORDER.concat(knownKeys.filter(k => !DEFAULT_PHASE_ORDER.includes(k)))
    }
    return DEFAULT_PHASE_ORDER
  })()

  const displayPhaseId = activePhase ?? (() => {
    const last = derivedOrder.slice().reverse().find(id => phases[id]?.status !== 'pending' && phases[id] != null)
    return last ?? null
  })()

  function handleSetViewMode(next: ViewMode) {
    setViewMode(next)
    writeViewMode(next)
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

  function handleDAGSelectTactician(filter: { phaseId: string; slotIdx: number } | null) {
    setSelectedTactician(filter)
    onSelectTactician?.(filter)
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
        <div className="flex items-center gap-1">
          {(['live', 'compact', 'dag'] as ViewMode[]).map((mode) => (
            <button
              key={mode}
              type="button"
              onClick={() => handleSetViewMode(mode)}
              className={[
                'text-[10px] px-1.5 py-0.5 rounded transition-colors select-none',
                viewMode === mode
                  ? 'bg-slate-700 text-slate-200'
                  : 'text-slate-500 hover:text-slate-300',
              ].join(' ')}
              title={
                mode === 'live' ? 'Phase DAG + swim lanes' :
                mode === 'compact' ? 'Compact legacy flow' :
                'Full investigation DAG'
              }
            >
              {mode === 'live' ? 'Live' : mode === 'compact' ? 'Compact' : 'DAG'}
            </button>
          ))}
        </div>
      </div>

      {viewMode === 'compact' ? (
        <div className="flex-1 overflow-hidden">
          <ResearchFlow runId={runId} compact />
        </div>
      ) : viewMode === 'dag' ? (
        <div className="flex-1 overflow-hidden">
          <InvestigationDAG runId={runId} onSelectTactician={handleDAGSelectTactician} />
        </div>
      ) : (
        /* Live view */
        <div className="flex flex-col flex-1 overflow-hidden">
          <PhaseProgress
            phases={phases}
            activePhase={activePhase}
            phaseOrder={derivedOrder}
          />
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
