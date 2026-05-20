import * as React from 'react'
import { cn } from '@/lib/utils'

/**
 * Pulsing placeholder for content that hasn't loaded yet.
 *
 * Pair with the real component: pin width/height to match the real component
 * so swapping skeleton → real causes zero layout shift.
 *
 * Example:
 *   <Skeleton className="h-4 w-32" />
 *   <Skeleton className="h-[60px] w-full rounded-md" />
 */
function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      data-slot="skeleton"
      aria-hidden="true"
      className={cn('animate-pulse rounded-md bg-muted/40', className)}
      {...props}
    />
  )
}

export { Skeleton }
