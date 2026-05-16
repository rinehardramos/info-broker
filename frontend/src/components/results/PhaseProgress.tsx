/**
 * PhaseProgress — horizontal phase strip for the v2 live view.
 *
 * Renders one pill per phase with status badge and a gate-result icon between
 * phases. The active phase is highlighted with a violet ring.  When no phase
 * data has arrived yet, shows 4 generic pending placeholder pills.
 */

import React from 'react'
import type { PhaseState, GateStatus } from '@/types/research'

interface PhaseProgressProps {
  phases: Record<string, PhaseState>
  activePhase: string | null
  /** Ordered list of phase ids from the strategy. */
  phaseOrder?: string[]
}

// Default placeholder order shown before the first is.phase_start arrives.
const DEFAULT_PHASE_ORDER = ['signal_extraction', 'broaden', 'red_team', 'rank_verify']

function statusColor(status: PhaseState['status']): string {
  switch (status) {
    case 'running':  return 'border-violet-500 bg-violet-950/60 text-violet-300'
    case 'passed':   return 'border-emerald-500 bg-emerald-950/40 text-emerald-300'
    case 'failed':   return 'border-rose-500 bg-rose-950/40 text-rose-300'
    case 'ask_user': return 'border-amber-400 bg-amber-950/40 text-amber-300'
    case 'skipped':  return 'border-slate-600 bg-slate-800/30 text-slate-500'
    default:         return 'border-slate-700 bg-slate-800/20 text-slate-500'
  }
}

function statusLabel(status: PhaseState['status']): string {
  switch (status) {
    case 'running':  return 'running'
    case 'passed':   return 'passed'
    case 'failed':   return 'failed'
    case 'ask_user': return 'needs input'
    case 'skipped':  return 'skipped'
    default:         return 'pending'
  }
}

function GateDivider({ gateStatus }: { gateStatus: GateStatus | null }) {
  if (!gateStatus) {
    return <div className="w-6 h-px bg-slate-700 flex-shrink-0 self-center" />
  }
  const icon = gateStatus === 'pass' ? '✓' : gateStatus === 'ask_user' ? '⚠' : '✗'
  const color = gateStatus === 'pass' ? 'text-emerald-400' : gateStatus === 'ask_user' ? 'text-amber-400' : 'text-rose-400'
  return (
    <div className={`flex-shrink-0 self-center text-xs font-bold ${color}`} title={`Gate: ${gateStatus}`}>
      {icon}
    </div>
  )
}

export function PhaseProgress({ phases, activePhase, phaseOrder }: PhaseProgressProps) {
  const order = phaseOrder && phaseOrder.length > 0 ? phaseOrder : DEFAULT_PHASE_ORDER

  return (
    <div
      className="flex items-center gap-1.5 px-3 py-2 border-b border-slate-800 bg-slate-900/50 overflow-x-auto flex-shrink-0"
      role="list"
      aria-label="Research phase progress"
    >
      {order.map((phaseId, idx) => {
        const phase = phases[phaseId] ?? { status: 'pending' as const, n_tacticians: 0, distinct_candidate_names: [], gate_status: null }
        const isActive = phaseId === activePhase
        const label = phaseId.replace(/_/g, ' ')
        const tacCount = phase.n_tacticians > 0 ? ` (${phase.n_tacticians} tactician${phase.n_tacticians !== 1 ? 's' : ''})` : ''

        return (
          <React.Fragment key={phaseId}>
            {idx > 0 && (
              <GateDivider gateStatus={order[idx - 1] ? (phases[order[idx - 1]]?.gate_status ?? null) : null} />
            )}
            <div
              role="listitem"
              className={[
                'flex-shrink-0 flex items-center gap-1 px-2.5 py-1 rounded-full border text-[11px] font-medium transition-all select-none',
                statusColor(phase.status),
                isActive ? 'ring-2 ring-violet-500 ring-offset-1 ring-offset-slate-900' : '',
              ].join(' ')}
              title={`${label}: ${statusLabel(phase.status)}${tacCount}`}
            >
              {isActive && (
                <span className="w-1.5 h-1.5 rounded-full bg-violet-400 animate-pulse flex-shrink-0" />
              )}
              <span>{label}</span>
              {phase.n_tacticians > 0 && (
                <span className="opacity-60 text-[10px]">·{phase.n_tacticians}t</span>
              )}
            </div>
          </React.Fragment>
        )
      })}
    </div>
  )
}
