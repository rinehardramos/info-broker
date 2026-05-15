/**
 * PhaseNode — rounded rect with status badge for use in the InvestigationDAG.
 */
import React from 'react'
import type { PhaseNodeData } from './buildDagFromRun'

function statusRing(status: PhaseNodeData['status']): string {
  switch (status) {
    case 'running':  return 'border-violet-500 bg-violet-950/70 text-violet-200'
    case 'passed':   return 'border-emerald-600 bg-emerald-950/60 text-emerald-200'
    case 'failed':   return 'border-rose-600 bg-rose-950/60 text-rose-300'
    case 'ask_user': return 'border-amber-500 bg-amber-950/60 text-amber-200'
    case 'skipped':  return 'border-slate-600 bg-slate-800/30 text-slate-500'
    default:         return 'border-slate-700 bg-slate-800/40 text-slate-500'
  }
}

function gateIcon(gateStatus: PhaseNodeData['gateStatus']): string {
  if (gateStatus === 'pass') return '✓'
  if (gateStatus === 'fail') return '✗'
  if (gateStatus === 'ask_user') return '⚠'
  return ''
}

interface PhaseNodeProps {
  data: PhaseNodeData
  onClick?: () => void
}

export function PhaseNode({ data, onClick }: PhaseNodeProps) {
  const label = data.phaseId.replace(/_/g, ' ')
  const gate = gateIcon(data.gateStatus)
  const isRunning = data.status === 'running'

  return (
    <button
      type="button"
      onClick={onClick}
      className={[
        'w-full h-full rounded-lg border px-2 py-1.5 flex flex-col gap-0.5 text-left transition-colors focus:outline-none focus-visible:ring-1 focus-visible:ring-violet-500',
        statusRing(data.status),
        onClick ? 'cursor-pointer hover:brightness-110' : 'cursor-default',
      ].join(' ')}
      title={`Phase: ${label} — ${data.status}${data.gateStatus ? ` (gate: ${data.gateStatus})` : ''}`}
    >
      <div className="flex items-center justify-between gap-1">
        <span className="text-[10px] font-semibold truncate leading-tight">{label}</span>
        {isRunning && (
          <span className="w-1.5 h-1.5 rounded-full bg-violet-400 animate-pulse flex-shrink-0" />
        )}
        {gate && !isRunning && (
          <span className={[
            'text-[10px] font-bold flex-shrink-0',
            data.gateStatus === 'pass' ? 'text-emerald-400' : data.gateStatus === 'ask_user' ? 'text-amber-400' : 'text-rose-400',
          ].join(' ')}>
            {gate}
          </span>
        )}
      </div>
      <span className="text-[9px] opacity-60 capitalize">{data.status}</span>
      {data.nTacticians > 0 && (
        <span className="text-[9px] opacity-50 tabular-nums">{data.nTacticians}t</span>
      )}
    </button>
  )
}
