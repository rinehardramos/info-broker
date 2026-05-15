/**
 * useReplay — rehydrate runStreamStore from research_trails so past runs
 * render CandidateComparison + ACH matrix + cards on resume.
 *
 * Called from LiveStream's resume button after the conversation has been
 * loaded. If the past run has a research_trail, this seeds the store with
 * the run's terminal state.
 */
import { api } from '@/api/client'
import { useRunStreamStore } from '@/stores/runStreamStore'
import type { ACHMatrix, RankedCandidate } from '@/types/research'

interface ReplayPayload {
  run_id: string
  query: string
  status: string
  terminate_reason: string | null
  phases: Record<string, {
    status: 'pending' | 'running' | 'passed' | 'failed' | 'ask_user' | 'skipped'
    n_tacticians: number
    distinct_candidate_names: string[]
    gate_status: 'pass' | 'fail' | 'ask_user' | null
  }>
  tacticians: Record<string, Record<string, {
    tactic_id: string
    forbidden_candidates: string[]
    candidate_names: string[]
    findings_count: number
    specialist_calls: number
  }>>
  cards: Array<{
    nodeId: string
    nodeName: string
    status: string
    preview: string
    output: unknown
    sources: Array<{ url?: string; label?: string; source_class?: string }>
    confidence?: number
    slotIdx?: number
    phaseId?: string
  }>
  ranked_candidates: RankedCandidate[]
  ach_matrix: ACHMatrix | null
}

/** Fetch + seed the store. Idempotent — calling twice for the same run is safe. */
export async function replayRunIntoStore(runId: string): Promise<boolean> {
  try {
    const { data } = await api.get<ReplayPayload>(`/v3/runs/${runId}/replay`)
    const store = useRunStreamStore.getState()

    // Seed phases
    for (const phaseId of Object.keys(data.phases)) {
      const ps = data.phases[phaseId]
      store.setPhaseTacticianCount(runId, phaseId, ps.n_tacticians)
      store.setPhaseStatus(runId, phaseId, ps.status)
      if (ps.gate_status !== null) {
        store.setPhaseComplete(runId, phaseId, ps.gate_status, ps.distinct_candidate_names)
      }
    }

    // Seed tacticians
    for (const phaseId of Object.keys(data.tacticians)) {
      const slots = data.tacticians[phaseId]
      for (const slotStr of Object.keys(slots)) {
        const t = slots[slotStr]
        const slotIdx = parseInt(slotStr, 10)
        store.addTactician(runId, phaseId, {
          slot_idx: slotIdx,
          tactic_id: t.tactic_id,
          forbidden_candidates: t.forbidden_candidates,
        })
        store.setTacticianResult(runId, phaseId, slotIdx, {
          candidate_names: t.candidate_names,
          findings_count: t.findings_count,
        })
      }
    }

    // Seed cards via hydrateFromServer (idempotent merge)
    if (data.cards.length > 0) {
      const cardsById: Record<string, unknown> = {}
      const cardOrder: string[] = []
      for (const c of data.cards) {
        cardsById[c.nodeId] = c
        cardOrder.push(c.nodeId)
      }
      store.hydrateFromServer(runId, {
        kind: 'is',
        status: data.status === 'completed' ? 'succeeded' : (data.status === 'terminated' ? 'failed' : 'ask_user') as never,
        cards: cardsById as never,
        cardOrder,
      })
    }

    // Seed ranked candidates + ACH matrix
    store.setRankedCandidates(runId, data.ranked_candidates)
    store.setAchMatrix(runId, data.ach_matrix)

    return true
  } catch (err) {
    // Non-fatal: legacy runs without a research_trails row simply have nothing to replay.
    console.warn('replayRunIntoStore: no replay available for', runId, err)
    return false
  }
}
