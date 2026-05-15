import React from 'react'
import type { SourceClass } from '@/types/research'

interface SourceClassBadgeProps {
  sourceClass: SourceClass
  /** When true, render as a compact icon-only pill (for inline use in card source lists). */
  compact?: boolean
}

const CLASS_CONFIG: Record<
  SourceClass,
  { icon: string; label: string; tooltip: string; colorClass: string }
> = {
  live_search: {
    icon: '🌐',
    label: 'Live',
    tooltip: 'Retrieved from a live web search during this run — freshest signal.',
    colorClass: 'bg-sky-950/60 text-sky-300 border-sky-800',
  },
  prior_research: {
    icon: '📚',
    label: 'Prior',
    tooltip:
      'Retrieved from prior research stored in the knowledge base (RAG). May be stale; treat as one hypothesis, not ground truth.',
    colorClass: 'bg-amber-950/60 text-amber-300 border-amber-800',
  },
  training_knowledge: {
    icon: '🧠',
    label: 'Training',
    tooltip:
      "Derived from the model's training knowledge. No external source was queried — lowest freshness.",
    colorClass: 'bg-violet-950/60 text-violet-300 border-violet-800',
  },
  primary_official: {
    icon: '🏛️',
    label: 'Official',
    tooltip: 'Primary official source: government registry, official database, or verified institutional record.',
    colorClass: 'bg-emerald-950/60 text-emerald-300 border-emerald-800',
  },
  primary_self: {
    icon: '👤',
    label: 'Self',
    tooltip: 'Primary self-reported source: the subject\'s own statements, social media, or official declarations.',
    colorClass: 'bg-rose-950/60 text-rose-300 border-rose-800',
  },
}

export function SourceClassBadge({ sourceClass, compact = false }: SourceClassBadgeProps) {
  const cfg = CLASS_CONFIG[sourceClass] ?? CLASS_CONFIG['training_knowledge']

  if (compact) {
    return (
      <span
        title={cfg.tooltip}
        className={`inline-flex items-center gap-0.5 text-[9px] font-semibold px-1 py-0.5 rounded border ${cfg.colorClass} cursor-help select-none`}
      >
        {cfg.icon}
      </span>
    )
  }

  return (
    <span
      title={cfg.tooltip}
      className={`inline-flex items-center gap-1 text-[10px] font-semibold px-1.5 py-0.5 rounded border ${cfg.colorClass} cursor-help select-none`}
    >
      {cfg.icon}
      <span>{cfg.label}</span>
    </span>
  )
}
