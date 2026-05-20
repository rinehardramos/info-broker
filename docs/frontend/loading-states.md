# Loading States — Coding Standard

Companion to `docs/operations/loading-ux-and-scale-out.md`. Quick reference for engineers
adding new data-driven UI. Every data view in this codebase must explicitly handle five states.

## The five states

Every `useQuery` / `useSuspenseQuery` consumer renders one of:

| State | When | Render |
|---|---|---|
| **Loading** | First fetch, no cached data | `<Skeleton>` matching the eventual shape |
| **Refreshing** | Refetch, previous data exists | Previous data + subtle pulse on changing slots |
| **Empty** | Query succeeded with zero items | `<EmptyState title=... hint=... />` |
| **Partial** | Some sibling queries failed | Render what worked; `<InlineError inline>` in the failed slot |
| **Error** | Critical fetch failed | `<InlineError title=... onRetry=... />` |

The two most-missed: **Empty** and **Partial**. Always handle both, not just happy path + spinner.

## Primitives

Located in `frontend/src/components/ui/`:

- `<Skeleton className="..." />` — pulsing placeholder. Match real-component dimensions exactly.
- `<EmptyState icon? title hint? action? compact? />` — zero-data state with mandatory title.
- `<InlineError title message? onRetry? inline? />` — error state with retry. Banned: "Something went wrong."
- `<PageShellSkeleton />` — top-level route Suspense fallback.

Hook: `useDebouncedLoading(isLoading, delayMs=250)` — suppresses sub-250ms loading flashes.

## Recipe — typical query consumer

```tsx
import { useQuery } from '@tanstack/react-query'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState } from '@/components/ui/empty-state'
import { InlineError } from '@/components/ui/inline-error'
import { useDebouncedLoading } from '@/hooks/useDebouncedLoading'

function FindingsList({ runId }: { runId: string }) {
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['findings', runId],
    queryFn: () => fetchFindings(runId),
  })

  const showSkeleton = useDebouncedLoading(isLoading)

  if (showSkeleton) {
    return (
      <div className="flex flex-col gap-2">
        <Skeleton className="h-[60px] w-full" />
        <Skeleton className="h-[60px] w-full" />
        <Skeleton className="h-[60px] w-full" />
      </div>
    )
  }

  if (isError) {
    return (
      <InlineError
        title="Couldn't load findings"
        message={(error as Error).message}
        onRetry={() => refetch()}
      />
    )
  }

  if (!data || data.length === 0) {
    return (
      <EmptyState
        title="No findings yet"
        hint="Findings appear here as the brain produces them."
      />
    )
  }

  return (
    <div className="flex flex-col gap-2">
      {data.map(f => <FindingRow key={f.id} finding={f} />)}
    </div>
  )
}
```

## Anti-patterns (banned)

1. Page-level spinners that hide already-loaded content.
2. Sub-250 ms loading flashes — use `useDebouncedLoading`.
3. Layout shift on data arrival — pin skeleton dimensions to real components.
4. `"Loading…"` text — use `<Skeleton>`.
5. Blank empty states — always use `<EmptyState>` with a title.
6. Generic errors — always use `<InlineError>` with a specific title.
7. Skeleton dimensions that don't match real components.
8. Blocking spinners on optimistic mutations.
9. Loading state shown on cache hits — use `staleTime` + `keepPreviousData`.
10. Same query refetched on every window focus — turned off globally in `lib/queryClient.ts`.

## React Query defaults (do not override casually)

Set in `lib/queryClient.ts`:

- `staleTime: 30_000` — most reads tolerate 30s staleness
- `gcTime: 5 * 60_000` — keeps queries warm for 5 min after last consumer unmounts
- `refetchOnWindowFocus: false` — avoid surprise refetches when switching tabs
- `retry: false on 4xx, up to 2 on 5xx` — don't retry user errors

Override per-query only when there's a documented reason.

## Stale-while-revalidate

When you need fresh data but want the previous value to stay visible during the refetch,
add `placeholderData: keepPreviousData`. The query renders the previous result while the
new one fetches; React Query handles the swap. No code change to consumers.

## Optimistic mutations

For predictable user actions (annotation save, status flip, mode change), use
`useMutation({ onMutate, onError, onSettled })` with cache writes in `onMutate` and
rollback in `onError`. Never render a blocking spinner on optimistic actions.
