import { create } from 'zustand'
import type { RankedCandidate, PhaseState, TacticianState } from '@/types/research'

export type NodeCardStatus = 'pending' | 'running' | 'streaming' | 'succeeded' | 'failed' | 'canceled'

export interface NodeCard {
  nodeId: string
  nodeName: string
  pluginOrTool?: string
  status: NodeCardStatus
  startedAt?: number
  finishedAt?: number
  preview: string
  output?: unknown
  sources?: Array<{ url?: string; label?: string }>
  injectedBy?: 'chat' | 'suggestion'
  // Tool input parameters (the full args the tool was called with).
  // Surfaced on the detail modal's Input tab.
  input?: Record<string, unknown>
  // IS-specific
  confidence?: number
  branchId?: string
  pir?: string
}

export interface BrainSuggestion {
  id: string
  kind: 'enrichment' | 'next-step' | 'strategy'
  action?: 'aggregate' | 'report' | 'presentation' | 'save-as-pipeline' | 'rerun-enriched' | 'inject'
  title: string
  body?: string
  payload?: Record<string, unknown>
  createdAt: number
}

export type RunKind = 'pipeline' | 'is'
export type RunStatus = 'running' | 'succeeded' | 'failed' | 'canceled'

export interface RunEdge {
  from: string
  to: string
  kind: 'result' | 'injected'
}

export interface RunStream {
  kind: RunKind
  status: RunStatus
  startedAt: number
  cardOrder: string[]
  cards: Record<string, NodeCard>
  edges: RunEdge[]
  suggestions: BrainSuggestion[]
  dismissedSuggestionIds: Set<string>
  hydratedFromServer: boolean
  /** Populated from is.run_complete event; empty array until run finishes. */
  rankedCandidates: RankedCandidate[]
  /** v2 engine phase tracking — populated by is.phase_start / is.phase_complete events. */
  phases: Record<string, PhaseState>
  /** v2 engine tactician tracking — populated by is.tactician_start / is.tactician_complete events. */
  tacticians: Record<string, Record<number, TacticianState>>
  /** The phase_id of the currently running phase, or null. */
  activePhase: string | null
}

interface RunStreamState {
  runsById: Record<string, RunStream>
  upsertCard: (runId: string, partial: Partial<NodeCard> & { nodeId: string }) => void
  appendStreamChunk: (runId: string, nodeId: string, chunk: string, seq: number) => void
  setRunStatus: (runId: string, kind: RunKind, status: RunStatus) => void
  addEdge: (runId: string, edge: RunEdge) => void
  addSuggestion: (runId: string, suggestion: BrainSuggestion) => void
  dismissSuggestion: (runId: string, id: string) => void
  hydrateFromServer: (runId: string, serverRun: Partial<RunStream>) => void
  clearRun: (runId: string) => void
  setRankedCandidates: (runId: string, candidates: RankedCandidate[]) => void
  // v2 phase actions
  setPhaseStatus: (runId: string, phaseId: string, status: PhaseState['status']) => void
  setPhaseTacticianCount: (runId: string, phaseId: string, n: number) => void
  setPhaseComplete: (runId: string, phaseId: string, gateStatus: PhaseState['gate_status'], distinctCandidateNames: string[]) => void
  addTactician: (runId: string, phaseId: string, state: Omit<TacticianState, 'candidate_names' | 'findings_count' | 'specialist_calls'> & { slot_idx: number }) => void
  setTacticianResult: (runId: string, phaseId: string, slotIdx: number, result: Pick<TacticianState, 'candidate_names' | 'findings_count'>) => void
}

const CANCELABLE_STATUSES: NodeCardStatus[] = ['running', 'streaming', 'pending']

const _chunkBuffer: Record<string, string> = {}
const _rafPending: Record<string, boolean> = {}

function ensureRun(
  runsById: Record<string, RunStream>,
  runId: string,
  kind: RunKind = 'pipeline',
): RunStream {
  if (!runsById[runId]) {
    runsById[runId] = {
      kind,
      status: 'running',
      startedAt: Date.now(),
      cardOrder: [],
      cards: {},
      edges: [],
      suggestions: [],
      dismissedSuggestionIds: new Set(),
      hydratedFromServer: false,
      rankedCandidates: [],
      phases: {},
      tacticians: {},
      activePhase: null,
    }
  } else {
    runsById[runId] = { ...runsById[runId] } // copy so mutations below don't touch old state
  }
  return runsById[runId]
}

export const useRunStreamStore = create<RunStreamState>()((set, get) => ({
  runsById: {},

  upsertCard(runId, partial) {
    set((state) => {
      const runsById = { ...state.runsById }
      const run = ensureRun(runsById, runId)
      const { nodeId, ...rest } = partial
      const existing = run.cards[nodeId]
      if (!existing && !run.cardOrder.includes(nodeId)) {
        run.cardOrder = [...run.cardOrder, nodeId]
      }
      const defaults: NodeCard = {
        nodeId,
        nodeName: nodeId,
        preview: '',
        status: 'pending',
      }
      run.cards = {
        ...run.cards,
        [nodeId]: Object.assign(defaults, existing ?? {}, rest, { nodeId }),
      }
      return { runsById }
    })
  },

  appendStreamChunk(runId, nodeId, chunk, _seq) {
    const bufKey = `${runId}:${nodeId}`
    _chunkBuffer[bufKey] = (_chunkBuffer[bufKey] ?? '') + chunk
    if (_rafPending[bufKey]) return
    _rafPending[bufKey] = true
    requestAnimationFrame(() => {
      const accumulated = _chunkBuffer[bufKey] ?? ''
      // Do NOT delete _chunkBuffer[bufKey] — it holds the full accumulated text
      delete _rafPending[bufKey]
      get().upsertCard(runId, { nodeId, status: 'streaming', preview: accumulated })
    })
  },

  setRunStatus(runId, kind, status) {
    set((state) => {
      const runsById = { ...state.runsById }
      const run = ensureRun(runsById, runId, kind)
      run.status = status
      // Upgrade-only kind classification: once a run is observed as 'is', never
      // downgrade it back to 'pipeline'. Some IS runs receive a generic
      // upsertCard before the first IS-specific event, which creates the run
      // with the default 'pipeline' kind. The IS event must be able to fix that.
      if (kind === 'is') run.kind = 'is'
      // Clean up streaming buffers for terminated runs
      if (status === 'succeeded' || status === 'failed' || status === 'canceled') {
        for (const key of Object.keys(_chunkBuffer)) {
          if (key.startsWith(`${runId}:`)) {
            delete _chunkBuffer[key]
            delete _rafPending[key]
          }
        }
      }
      if (status === 'canceled') {
        const updatedCards = { ...run.cards }
        for (const [id, card] of Object.entries(updatedCards)) {
          if (CANCELABLE_STATUSES.includes(card.status)) {
            updatedCards[id] = { ...card, status: 'canceled' }
          }
        }
        run.cards = updatedCards
      }
      return { runsById }
    })
  },

  addEdge(runId, edge) {
    set((state) => {
      const runsById = { ...state.runsById }
      const run = ensureRun(runsById, runId)
      run.edges = [...run.edges, edge]
      return { runsById }
    })
  },

  addSuggestion(runId, suggestion) {
    set((state) => {
      const runsById = { ...state.runsById }
      const run = ensureRun(runsById, runId)
      run.suggestions = [...run.suggestions, suggestion]
      return { runsById }
    })
  },

  dismissSuggestion(runId, id) {
    set((state) => {
      const runsById = { ...state.runsById }
      if (!runsById[runId]) return state
      const dismissed = new Set(runsById[runId].dismissedSuggestionIds)
      dismissed.add(id)
      runsById[runId] = { ...runsById[runId], dismissedSuggestionIds: dismissed }
      return { runsById }
    })
  },

  hydrateFromServer(runId, serverRun) {
    set((state) => {
      const runsById = { ...state.runsById }
      ensureRun(runsById, runId)
      const merged = { ...runsById[runId], ...serverRun, hydratedFromServer: true }
      // Coerce to Set in case JSON deserialization sent an array
      merged.dismissedSuggestionIds = new Set(merged.dismissedSuggestionIds)
      runsById[runId] = merged
      return { runsById }
    })
  },

  clearRun(runId) {
    // Clean up any dangling chunk buffers for this run
    for (const key of Object.keys(_chunkBuffer)) {
      if (key.startsWith(`${runId}:`)) {
        delete _chunkBuffer[key]
        delete _rafPending[key]
      }
    }
    set((state) => {
      const { [runId]: _, ...rest } = state.runsById
      return { runsById: rest }
    })
  },

  setRankedCandidates(runId, candidates) {
    set((state) => {
      const runsById = { ...state.runsById }
      const run = ensureRun(runsById, runId, 'is')
      run.rankedCandidates = candidates
      return { runsById }
    })
  },

  setPhaseStatus(runId, phaseId, status) {
    set((state) => {
      const runsById = { ...state.runsById }
      const run = ensureRun(runsById, runId, 'is')
      const existing = run.phases[phaseId] ?? { status: 'pending', n_tacticians: 0, distinct_candidate_names: [], gate_status: null }
      run.phases = { ...run.phases, [phaseId]: { ...existing, status } }
      if (status === 'running') run.activePhase = phaseId
      return { runsById }
    })
  },

  setPhaseTacticianCount(runId, phaseId, n) {
    set((state) => {
      const runsById = { ...state.runsById }
      const run = ensureRun(runsById, runId, 'is')
      const existing = run.phases[phaseId] ?? { status: 'pending', n_tacticians: 0, distinct_candidate_names: [], gate_status: null }
      run.phases = { ...run.phases, [phaseId]: { ...existing, n_tacticians: n } }
      return { runsById }
    })
  },

  setPhaseComplete(runId, phaseId, gateStatus, distinctCandidateNames) {
    set((state) => {
      const runsById = { ...state.runsById }
      const run = ensureRun(runsById, runId, 'is')
      const existing = run.phases[phaseId] ?? { status: 'pending', n_tacticians: 0, distinct_candidate_names: [], gate_status: null }
      const newStatus: PhaseState['status'] = gateStatus === 'pass' ? 'passed' : gateStatus === 'ask_user' ? 'ask_user' : 'failed'
      run.phases = {
        ...run.phases,
        [phaseId]: { ...existing, status: newStatus, gate_status: gateStatus, distinct_candidate_names: distinctCandidateNames },
      }
      if (run.activePhase === phaseId) run.activePhase = null
      return { runsById }
    })
  },

  addTactician(runId, phaseId, { slot_idx, tactic_id, forbidden_candidates }) {
    set((state) => {
      const runsById = { ...state.runsById }
      const run = ensureRun(runsById, runId, 'is')
      const phaseTacticians = run.tacticians[phaseId] ?? {}
      run.tacticians = {
        ...run.tacticians,
        [phaseId]: {
          ...phaseTacticians,
          [slot_idx]: {
            tactic_id,
            forbidden_candidates: forbidden_candidates ?? [],
            candidate_names: [],
            findings_count: 0,
            specialist_calls: 0,
          },
        },
      }
      return { runsById }
    })
  },

  setTacticianResult(runId, phaseId, slotIdx, { candidate_names, findings_count }) {
    set((state) => {
      const runsById = { ...state.runsById }
      const run = ensureRun(runsById, runId, 'is')
      const phaseTacticians = run.tacticians[phaseId] ?? {}
      const existing = phaseTacticians[slotIdx]
      if (!existing) return state
      run.tacticians = {
        ...run.tacticians,
        [phaseId]: {
          ...phaseTacticians,
          [slotIdx]: { ...existing, candidate_names, findings_count },
        },
      }
      return { runsById }
    })
  },
}))

// Debug-only: expose the store on window for E2E inspection and devtools.
// Stripped by Vite in production builds.
if (typeof window !== 'undefined' && import.meta.env.DEV) {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  ;(window as any).useRunStreamStore = useRunStreamStore
}
