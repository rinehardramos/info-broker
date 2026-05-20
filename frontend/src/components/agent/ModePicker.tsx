import { useQuery } from '@tanstack/react-query'
import { listModes } from '@/api/v3'
import { useModeStore } from '@/stores/modeStore'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

/**
 * Pill row of available Modes. Persists selection in modeStore (localStorage).
 *
 * Layout: compact, single horizontal row. Recolor on hover, accent border on
 * active. Tooltip carries the mode description. Renders a short skeleton on
 * first load; subsequent loads serve from React Query cache instantly.
 */
export function ModePicker({ className }: { className?: string }) {
  const { modeId, setModeId } = useModeStore()
  const { data: modes, isLoading } = useQuery({
    queryKey: ['modes'],
    queryFn: listModes,
    staleTime: 24 * 60 * 60_000, // bundled modes change with deploys, not at runtime
  })

  if (isLoading || !modes) {
    return (
      <div className={cn('flex items-center gap-1.5', className)}>
        <Skeleton className="h-6 w-16" />
        <Skeleton className="h-6 w-20" />
        <Skeleton className="h-6 w-20" />
        <Skeleton className="h-6 w-18" />
      </div>
    )
  }

  const current = modeId ?? 'general'

  return (
    <div className={cn('flex items-center gap-1.5 flex-wrap', className)}>
      <span className="text-[10px] opacity-50 uppercase tracking-wider mr-1">Mode</span>
      {modes.map((m) => {
        const active = m.id === current
        return (
          <button
            key={m.id}
            type="button"
            onClick={() => setModeId(m.id)}
            title={m.description}
            className={cn(
              'rounded text-[11px] px-2 py-1 font-medium border transition-colors',
              active
                ? 'border-[color:var(--accent)] text-[color:var(--accent)] bg-[color:var(--accent)]/10'
                : 'border-[color:var(--border)] text-[color:var(--subtext)] hover:text-[color:var(--text)] hover:border-[color:var(--accent)]/50',
            )}
          >
            {m.label}
          </button>
        )
      })}
    </div>
  )
}
