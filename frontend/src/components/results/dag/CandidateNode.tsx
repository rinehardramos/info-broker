/**
 * CandidateNode — final ranked candidate node showing rank, name, confidence.
 */
import React from 'react'
import type { CandidateNodeData } from './buildDagFromRun'

const RANK_COLORS = [
  'border-violet-500 bg-violet-950/70 text-violet-100',
  'border-slate-500 bg-slate-800/70 text-slate-200',
  'border-amber-700 bg-amber-950/60 text-amber-200',
]

interface CandidateNodeProps {
  data: CandidateNodeData
  onClick?: () => void
}

export function CandidateNode({ data, onClick }: CandidateNodeProps) {
  const pct = Math.round(Math.min(1, Math.max(0, data.confidence)) * 100)
  const colorCls = RANK_COLORS[data.rank - 1] ?? RANK_COLORS[2]

  return (
    <button
      type="button"
      onClick={onClick}
      className={[
        'w-full h-full rounded-lg border px-2 py-1.5 flex flex-col gap-1 text-left transition-colors focus:outline-none focus-visible:ring-1 focus-visible:ring-violet-500',
        colorCls,
        onClick ? 'cursor-pointer hover:brightness-110' : 'cursor-default',
      ].join(' ')}
      title={`#${data.rank}: ${data.name} — ${pct}% confidence`}
    >
      <div className="flex items-center justify-between gap-1">
        <span className="text-[9px] font-bold opacity-70">#{data.rank}</span>
        <span className="text-[9px] font-bold tabular-nums text-right">{pct}%</span>
      </div>
      <div className="text-[10px] font-semibold truncate leading-tight" title={data.name}>
        {data.name}
      </div>
      {/* Confidence bar */}
      <div className="h-1 rounded bg-current/20 overflow-hidden">
        <div className="h-full rounded bg-current/60" style={{ width: `${pct}%` }} />
      </div>
    </button>
  )
}
