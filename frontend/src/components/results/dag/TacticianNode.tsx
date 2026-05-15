/**
 * TacticianNode — column-like card showing slot, tactic, candidate(s), and lock icon.
 */
import React from 'react'
import type { TacticianNodeData } from './buildDagFromRun'

function LockIcon() {
  return (
    <svg width="9" height="9" viewBox="0 0 16 16" fill="none" aria-hidden="true" className="opacity-40 flex-shrink-0">
      <rect x="3" y="7" width="10" height="8" rx="2" fill="currentColor" />
      <path d="M5 7V5a3 3 0 016 0v2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" fill="none" />
    </svg>
  )
}

interface TacticianNodeProps {
  data: TacticianNodeData
  onClick?: () => void
}

export function TacticianNode({ data, onClick }: TacticianNodeProps) {
  const topCandidate = data.candidateNames[0] ?? null
  const extraCount = data.candidateNames.length - 1

  return (
    <button
      type="button"
      onClick={onClick}
      className={[
        'w-full h-full rounded-md border px-2 py-1 flex flex-col gap-0.5 text-left transition-colors focus:outline-none focus-visible:ring-1 focus-visible:ring-violet-500',
        'border-slate-700 bg-slate-800/50 hover:border-slate-500 hover:bg-slate-800/80',
        onClick ? 'cursor-pointer' : 'cursor-default',
      ].join(' ')}
      title={`Slot ${data.slotIdx} · ${data.tacticId || 'unknown'}${data.hasForbidden ? ' (has forbidden candidates)' : ''}`}
    >
      <div className="flex items-center justify-between gap-1">
        <span className="text-[9px] font-bold text-slate-400 truncate">
          s{data.slotIdx}
          {data.tacticId ? ` · ${data.tacticId.replace(/_/g, ' ')}` : ''}
        </span>
        {data.hasForbidden && <LockIcon />}
      </div>

      {topCandidate ? (
        <div className="text-[9px] text-emerald-300 truncate font-medium leading-tight" title={topCandidate}>
          {topCandidate}
        </div>
      ) : (
        <div className="text-[9px] text-slate-600 italic leading-tight">—</div>
      )}

      {extraCount > 0 && (
        <div className="text-[8px] text-slate-500 leading-tight">+{extraCount} more</div>
      )}

      {data.findingsCount > 0 && (
        <div className="text-[8px] text-slate-600 mt-auto leading-tight tabular-nums">
          {data.findingsCount}f
        </div>
      )}
    </button>
  )
}
