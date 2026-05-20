import * as React from 'react'
import { cn } from '@/lib/utils'

type InlineErrorProps = {
  title: string
  message?: string
  onRetry?: () => void
  className?: string
  inline?: boolean
}

export function InlineError({
  title,
  message,
  onRetry,
  className,
  inline = false,
}: InlineErrorProps) {
  return (
    <div
      role="alert"
      data-slot="inline-error"
      className={cn(
        'flex flex-col gap-1 text-sm',
        inline
          ? 'text-destructive'
          : 'rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-destructive',
        className,
      )}
    >
      <div className="font-medium">{title}</div>
      {message ? (
        <div className="text-xs opacity-80 break-words">{message}</div>
      ) : null}
      {onRetry ? (
        <button
          type="button"
          onClick={onRetry}
          className="mt-1 inline-flex w-fit items-center rounded border border-destructive/40 px-2 py-0.5 text-xs font-medium hover:bg-destructive/10 focus:outline-none focus-visible:ring-2 focus-visible:ring-destructive/50"
        >
          Retry
        </button>
      ) : null}
    </div>
  )
}
