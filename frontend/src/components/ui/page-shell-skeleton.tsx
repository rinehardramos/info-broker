import { Skeleton } from '@/components/ui/skeleton'

export function PageShellSkeleton() {
  return (
    <div className="flex h-screen flex-col">
      <div className="flex h-12 items-center gap-3 border-b border-border px-4">
        <Skeleton className="h-6 w-6 rounded-full" />
        <Skeleton className="h-4 w-32" />
        <div className="ml-auto flex items-center gap-2">
          <Skeleton className="h-6 w-20" />
          <Skeleton className="h-6 w-6 rounded-full" />
        </div>
      </div>
      <div className="flex flex-1 overflow-hidden">
        <aside className="hidden w-56 shrink-0 flex-col gap-2 border-r border-border p-3 md:flex">
          <Skeleton className="h-7 w-full" />
          <Skeleton className="h-7 w-4/5" />
          <Skeleton className="h-7 w-3/5" />
          <Skeleton className="mt-4 h-7 w-full" />
          <Skeleton className="h-7 w-4/5" />
        </aside>
        <main className="flex flex-1 flex-col gap-4 overflow-y-auto p-4">
          <Skeleton className="h-7 w-48" />
          <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
            <Skeleton className="h-28 w-full" />
            <Skeleton className="h-28 w-full" />
            <Skeleton className="h-28 w-full" />
          </div>
          <Skeleton className="h-5 w-32" />
          <div className="flex flex-col gap-2">
            <Skeleton className="h-12 w-full" />
            <Skeleton className="h-12 w-full" />
            <Skeleton className="h-12 w-full" />
            <Skeleton className="h-12 w-full" />
          </div>
        </main>
      </div>
    </div>
  )
}
