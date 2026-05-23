// frontend/src/hooks/useGateDetail.ts
//
// Fetches admin-only gate detail for an ask_user run. The server returns
// 403 for non-admin callers regardless of run ownership, so we only enable
// the query when the caller is admin. See spec:
// docs/superpowers/specs/2026-05-22-gather-ask-user-diagnostic-design.md.

import { useQuery } from '@tanstack/react-query'
import type { GateDetailResponse } from '@/types/gate'
import { api } from '../api/client'

export function useGateDetail(runId: string | null | undefined, enabled: boolean) {
  return useQuery({
    queryKey: ['gate-detail', runId],
    queryFn: async (): Promise<GateDetailResponse> => {
      const r = await api.get<GateDetailResponse>(`/v3/pipelines/runs/${runId}/gate-detail`)
      return r.data
    },
    enabled: enabled && Boolean(runId),
    retry: false,
    staleTime: 60_000,
  })
}
