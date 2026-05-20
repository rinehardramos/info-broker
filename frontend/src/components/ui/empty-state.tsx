import * as React from 'react'
import { cn } from '@/lib/utils'

type EmptyStateProps = {
  icon?: React.ReactNode
  title: string
  hint?: React.ReactNode
  action?: React.ReactNode
  className?: string
  compact?: boolean
}

export function EmptyState({
  icon,
  title,
  hint,
  action,
  className,
  compact = false,
}: EmptyStateProps) {
  return (
    <div
      role="status"
      data-slot="empty-state"
      className={cn(
        'flex flex-col items-center justify-center gap-2 text-center text-sm',
        compact ? 'py-4' : 'py-10',
        className,
      )}
    >
      {icon ? <div className="text-muted-foreground/70">{icon}</div> : null}
      <div className="font-medium text-foreground/90">{title}</div>
      {hint ? <div className="max-w-sm text-xs text-muted-foreground">{hint}</div> : null}
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  )
}
