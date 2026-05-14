import { create } from 'zustand'

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
}))
