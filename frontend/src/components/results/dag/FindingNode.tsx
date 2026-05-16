/**
 * FindingNode — small node colored by source_class.
 */
import React from 'react'
import type { FindingNodeData } from './buildDagFromRun'
import type { SourceClass } from '@/types/research'

const SOURCE_CLASS_COLORS: Record<SourceClass, string> = {
  live_search:        'border-sky-700 bg-sky-950/60 text-sky-300',
  prior_research:     'border-amber-700 bg-amber-950/60 text-amber-300',
  training_knowledge: 'border-violet-700 bg-violet-950/60 text-violet-300',
  primary_official:   'border-emerald-700 bg-emerald-950/60 text-emerald-300',
  primary_self:       'border-rose-700 bg-rose-950/60 text-rose-300',
}

const SOURCE_CLASS_ICONS: Record<SourceClass, string> = {
  live_search:        '🌐',
  prior_research:     '📚',
  training_knowledge: '🧠',
  primary_official:   '🏛️',
  primary_self:       '👤',
}

interface FindingNodeProps {
  data: FindingNodeData
  onClick?: () => void
}

export function FindingNode({ data, onClick }: FindingNodeProps) {
  const cls = data.sourceClass ?? 'training_knowledge'
  const colorCls = SOURCE_CLASS_COLORS[cls]
  const icon = SOURCE_CLASS_ICONS[cls]

  return (
    <button
      type="button"
      onClick={onClick}
      className={[
        'w-full h-full rounded border px-1.5 py-1 flex items-center gap-1 transition-colors focus:outline-none focus-visible:ring-1 focus-visible:ring-violet-500',
        colorCls,
        onClick ? 'cursor-pointer hover:brightness-110' : 'cursor-default',
      ].join(' ')}
      title={`Finding ${data.findingIdx + 1} · source: ${cls.replace(/_/g, ' ')}`}
    >
      <span className="text-[9px] flex-shrink-0">{icon}</span>
      <span className="text-[9px] font-medium truncate leading-tight">{data.label}</span>
    </button>
  )
}
