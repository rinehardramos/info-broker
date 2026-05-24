/**
 * buildDagFromRun — pure function that derives a positioned DAG from RunStream state.
 *
 * Returns {nodes, edges} ready for hand-rolled absolute-positioned rendering.
 * No external deps — easy to unit test.
 *
 * Layout strategy: topological top-to-bottom.
 *   Row 0 (y=0):    1 Query root node
 *   Row 1..N:        Phase nodes, one per phase in order
 *     Sub-row:       Tactician nodes below each phase, spread horizontally
 *     Sub-sub-row:   Finding nodes (≤MAX_FINDINGS_PER_TACTICIAN per tactician)
 *   Final row:       Top-3 RankedCandidate nodes
 *
 * Coordinates are in logical pixels (caller scales via CSS transform if needed).
 */

import type { RunStream } from '@/stores/runStreamStore'
import type { PhaseState, TacticianState, SourceClass } from '@/types/research'

// ─── Node / Edge types ────────────────────────────────────────────────────────

export type DagNodeKind = 'query' | 'phase' | 'tactician' | 'finding' | 'candidate'

export interface QueryNodeData {
  kind: 'query'
  label: string
}

export interface PhaseNodeData {
  kind: 'phase'
  phaseId: string
  status: PhaseState['status']
  gateStatus: PhaseState['gate_status']
  nTacticians: number
}

export interface TacticianNodeData {
  kind: 'tactician'
  phaseId: string
  slotIdx: number
  tacticId: string
  candidateNames: string[]
  hasForbidden: boolean
  findingsCount: number
}

export interface FindingNodeData {
  kind: 'finding'
  phaseId: string
  slotIdx: number
  /** Synthetic index within this tactician (0-based) */
  findingIdx: number
  sourceClass: SourceClass | null
  label: string
}

export interface CandidateNodeData {
  kind: 'candidate'
  rank: number
  name: string
  confidence: number
  slotIdx: number
  /** True if the candidate has at least one disconfirm evidence row. */
  isPruned?: boolean
  /** Short reason from the first disconfirm snippet (≤ 60 chars), if any. */
  pruneReason?: string
}

export type DagNodeData =
  | QueryNodeData
  | PhaseNodeData
  | TacticianNodeData
  | FindingNodeData
  | CandidateNodeData

export interface DagNode {
  id: string
  x: number
  y: number
  width: number
  height: number
  data: DagNodeData
}

export interface DagEdge {
  id: string
  sourceId: string
  targetId: string
  /** Optional inline label rendered at the edge midpoint (e.g. "pass · 3"). */
  label?: string
  /** Used to color the label: green for pass, red for fail, amber for ask_user. */
  labelKind?: 'pass' | 'fail' | 'ask_user'
}

export interface DagGraph {
  nodes: DagNode[]
  edges: DagEdge[]
  totalWidth: number
  totalHeight: number
}

// ─── Layout constants ─────────────────────────────────────────────────────────

/** Max finding nodes rendered per tactician (prevents graph explosion). */
export const MAX_FINDINGS_PER_TACTICIAN = 3

const NODE_W = {
  query: 140,
  phase: 160,
  tactician: 130,
  finding: 90,
  candidate: 140,
} satisfies Record<DagNodeKind, number>

const NODE_H = {
  query: 40,
  phase: 52,
  tactician: 64,
  finding: 36,
  candidate: 56,
} satisfies Record<DagNodeKind, number>

const ROW_GAP = 32   // vertical gap between rows
const COL_GAP = 16   // horizontal gap between siblings

// Default phase order (mirrors PhaseDAGView)
const DEFAULT_PHASE_ORDER = ['extract', 'gather', 'disconfirm', 'synthesize']

// ─── Source class inference ───────────────────────────────────────────────────

/**
 * Finding nodes are synthesized from TacticianState.findings_count (we don't
 * have per-finding records in the store). We infer a round-robin source class
 * for coloring so the graph is informative even without per-finding metadata.
 */
const ROUND_ROBIN_CLASSES: SourceClass[] = [
  'live_search',
  'primary_official',
  'prior_research',
  'training_knowledge',
  'primary_self',
]

function syntheticSourceClass(idx: number): SourceClass {
  return ROUND_ROBIN_CLASSES[idx % ROUND_ROBIN_CLASSES.length]
}

// ─── Main function ────────────────────────────────────────────────────────────

export function buildDagFromRun(run: RunStream | undefined): DagGraph {
  if (!run) return { nodes: [], edges: [], totalWidth: 0, totalHeight: 0 }

  const nodes: DagNode[] = []
  const edges: DagEdge[] = []

  // Determine phase order
  const knownPhaseKeys = Object.keys(run.phases)
  const phaseOrder = (() => {
    const base = DEFAULT_PHASE_ORDER.concat(
      knownPhaseKeys.filter(k => !DEFAULT_PHASE_ORDER.includes(k)),
    )
    // Only include phases that actually exist in the run
    return base.filter(id => run.phases[id] != null || knownPhaseKeys.includes(id))
  })()

  // ── Row 0: Query root ──────────────────────────────────────────────────────
  const queryId = 'node__query'
  let currentY = 0

  // Will center horizontally once we know total width — placeholder x=0 for now
  nodes.push({
    id: queryId,
    x: 0, // centered later
    y: currentY,
    width: NODE_W.query,
    height: NODE_H.query,
    data: { kind: 'query', label: 'Query' },
  })

  currentY += NODE_H.query + ROW_GAP

  // ── Phase rows ─────────────────────────────────────────────────────────────
  let prevPhaseId: string | null = null

  for (const phaseId of phaseOrder) {
    const phaseState: PhaseState = run.phases[phaseId] ?? {
      status: 'pending',
      n_tacticians: 0,
      distinct_candidate_names: [],
      gate_status: null,
    }
    const phaseTacticians: Record<number, TacticianState> = run.tacticians[phaseId] ?? {}
    const tacSlots = Object.entries(phaseTacticians)
      .map(([k, v]) => ({ slotIdx: parseInt(k, 10), state: v }))
      .sort((a, b) => a.slotIdx - b.slotIdx)

    const phaseNodeId = `node__phase__${phaseId}`

    // Phase node — x centered later
    nodes.push({
      id: phaseNodeId,
      x: 0,
      y: currentY,
      width: NODE_W.phase,
      height: NODE_H.phase,
      data: {
        kind: 'phase',
        phaseId,
        status: phaseState.status,
        gateStatus: phaseState.gate_status,
        nTacticians: phaseState.n_tacticians,
      },
    })

    // Edge: query → first phase, prev phase → this phase. Carry the prev
    // phase's gate decision on the edge so the reader sees pass·N / fail·N /
    // ask_user as the run progresses.
    if (prevPhaseId === null) {
      edges.push({ id: `edge__query__${phaseId}`, sourceId: queryId, targetId: phaseNodeId })
    } else {
      const prevState = run.phases[prevPhaseId]
      const prevGate = prevState?.gate_status ?? null
      const prevCount = (prevState?.distinct_candidate_names ?? []).length
      let label: string | undefined
      let labelKind: DagEdge['labelKind']
      if (prevGate === 'pass') {
        label = `pass · ${prevCount}`
        labelKind = 'pass'
      } else if (prevGate === 'fail') {
        label = `fail · ${prevCount}`
        labelKind = 'fail'
      } else if (prevGate === 'ask_user') {
        label = 'ask user'
        labelKind = 'ask_user'
      }
      edges.push({
        id: `edge__${prevPhaseId}__${phaseId}`,
        sourceId: `node__phase__${prevPhaseId}`,
        targetId: phaseNodeId,
        label,
        labelKind,
      })
    }
    prevPhaseId = phaseId

    currentY += NODE_H.phase + ROW_GAP

    if (tacSlots.length === 0) continue

    // ── Tactician row ────────────────────────────────────────────────────────
    // Calculate total width of tactician row to center it
    const tacRowY = currentY

    for (const { slotIdx, state } of tacSlots) {
      const tacNodeId = `node__tac__${phaseId}__${slotIdx}`
      // x is placeholder — resolved in the centering pass below
      nodes.push({
        id: tacNodeId,
        x: 0,
        y: tacRowY,
        width: NODE_W.tactician,
        height: NODE_H.tactician,
        data: {
          kind: 'tactician',
          phaseId,
          slotIdx,
          tacticId: state.tactic_id,
          candidateNames: state.candidate_names,
          hasForbidden: state.forbidden_candidates.length > 0,
          findingsCount: state.findings_count,
        },
      })
      edges.push({
        id: `edge__${phaseId}__tac__${slotIdx}`,
        sourceId: phaseNodeId,
        targetId: tacNodeId,
      })
    }

    currentY += NODE_H.tactician + ROW_GAP

    // ── Finding nodes ────────────────────────────────────────────────────────
    let hasFindingNodes = false

    for (const { slotIdx, state } of tacSlots) {
      const count = Math.min(state.findings_count, MAX_FINDINGS_PER_TACTICIAN)
      if (count === 0) continue
      hasFindingNodes = true

      const tacNodeId = `node__tac__${phaseId}__${slotIdx}`
      for (let fi = 0; fi < count; fi++) {
        const findingNodeId = `node__finding__${phaseId}__${slotIdx}__${fi}`
        nodes.push({
          id: findingNodeId,
          x: 0,
          y: currentY,
          width: NODE_W.finding,
          height: NODE_H.finding,
          data: {
            kind: 'finding',
            phaseId,
            slotIdx,
            findingIdx: fi,
            sourceClass: syntheticSourceClass(fi),
            label: `Finding ${fi + 1}`,
          },
        })
        edges.push({
          id: `edge__finding__${phaseId}__${slotIdx}__${fi}`,
          sourceId: tacNodeId,
          targetId: findingNodeId,
        })
      }
    }

    if (hasFindingNodes) {
      currentY += NODE_H.finding + ROW_GAP
    }
  }

  // ── Final row: top-3 ranked candidates ────────────────────────────────────
  // Pruned candidates (those with disconfirm evidence) stay in the row but
  // render dim so the reader can see what was rejected and why.
  const top3 = run.rankedCandidates.slice(0, 3)
  if (top3.length > 0) {
    const candidateRowY = currentY
    const lastPhaseNodeId = prevPhaseId ? `node__phase__${prevPhaseId}` : queryId

    for (let i = 0; i < top3.length; i++) {
      const c = top3[i]
      const candNodeId = `node__candidate__${i}`
      const disconfirms = (c.evidence ?? []).filter((e) => e.is_disconfirm)
      const isPruned = disconfirms.length > 0
      const firstReason = isPruned ? (disconfirms[0].snippet ?? '').slice(0, 60) : undefined
      nodes.push({
        id: candNodeId,
        x: 0,
        y: candidateRowY,
        width: NODE_W.candidate,
        height: NODE_H.candidate,
        data: {
          kind: 'candidate',
          rank: i + 1,
          name: c.name,
          confidence: c.confidence,
          slotIdx: c.slot_idx,
          isPruned,
          pruneReason: firstReason,
        },
      })
      edges.push({
        id: `edge__candidate__${i}`,
        sourceId: lastPhaseNodeId,
        targetId: candNodeId,
      })
    }

    currentY += NODE_H.candidate
  }

  // ── Horizontal layout pass ────────────────────────────────────────────────
  // Assign x coordinates by grouping nodes per y-row and spreading them evenly.
  const byRow = new Map<number, DagNode[]>()
  for (const n of nodes) {
    const row = byRow.get(n.y) ?? []
    row.push(n)
    byRow.set(n.y, row)
  }

  let maxRowWidth = 0
  for (const row of byRow.values()) {
    const rowWidth = row.reduce((sum, n) => sum + n.width, 0) + COL_GAP * (row.length - 1)
    if (rowWidth > maxRowWidth) maxRowWidth = rowWidth
  }

  const totalWidth = Math.max(maxRowWidth, NODE_W.query)

  for (const row of byRow.values()) {
    const rowWidth = row.reduce((sum, n) => sum + n.width, 0) + COL_GAP * (row.length - 1)
    let xCursor = Math.round((totalWidth - rowWidth) / 2)
    for (const n of row) {
      n.x = xCursor
      xCursor += n.width + COL_GAP
    }
  }

  return { nodes, edges, totalWidth, totalHeight: currentY }
}
