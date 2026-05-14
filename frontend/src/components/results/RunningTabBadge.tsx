import React from 'react'
import { useRunStreamStore } from '@/stores/runStreamStore'
import { cn } from '@/lib/utils'

interface RunningTabBadgeProps {
  runId: string
  label: string
}

export function RunningTabBadge({ runId, label }: RunningTabBadgeProps) {
  const status = useRunStreamStore((s) => s.runsById[runId]?.status)
  const isRunning = status === 'running'

  return (
    <span className="flex items-center gap-1.5">
      <span
        className={cn(
          'inline-block w-1.5 h-1.5 rounded-full flex-shrink-0',
          isRunning
            ? 'bg-amber-400 animate-pulse'
            : status === 'succeeded'
            ? 'bg-green-500'
            : status === 'failed'
            ? 'bg-red-500'
            : 'bg-muted-foreground',
        )}
      />
      {label}
    </span>
  )
}
