import { Skeleton } from '@/components/ui/skeleton'

/**
 * Pre-data placeholder for EstimateBreakdown. Matches the eventual layout:
 *   summary line (~X RU · ~Y min · ~Z calls)  +  wallet line below.
 */
export function EstimateBreakdownSkeleton() {
  return (
    <div style={{ marginBottom: 10 }} aria-busy="true">
      <div className="flex items-center gap-2">
        <Skeleton className="h-3.5 w-24" />
        <Skeleton className="h-3.5 w-16" />
        <Skeleton className="h-3.5 w-20" />
      </div>
      <div className="mt-2">
        <Skeleton className="h-3 w-56" />
      </div>
    </div>
  )
}
