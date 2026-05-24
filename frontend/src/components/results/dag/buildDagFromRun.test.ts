import { describe, it, expect } from 'vitest'
import { buildDagFromRun, MAX_FINDINGS_PER_TACTICIAN } from './buildDagFromRun'
import type { RunStream } from '@/stores/runStreamStore'

// Minimal RunStream factory
function makeRun(overrides: Partial<RunStream> = {}): RunStream {
  return {
    kind: 'is',
    status: 'running',
    startedAt: 0,
    cardOrder: [],
    cards: {},
    edges: [],
    suggestions: [],
    dismissedSuggestionIds: new Set(),
    hydratedFromServer: false,
    rankedCandidates: [],
    achMatrix: null,
    phases: {},
    tacticians: {},
    activePhase: null,
    ...overrides,
  }
}

describe('buildDagFromRun', () => {
  it('returns empty graph for undefined run', () => {
    const g = buildDagFromRun(undefined)
    expect(g.nodes).toHaveLength(0)
    expect(g.edges).toHaveLength(0)
    expect(g.totalWidth).toBe(0)
    expect(g.totalHeight).toBe(0)
  })

  it('returns only the query node when no phases exist', () => {
    const g = buildDagFromRun(makeRun())
    expect(g.nodes).toHaveLength(1)
    const queryNode = g.nodes[0]
    expect(queryNode.data.kind).toBe('query')
    expect(g.edges).toHaveLength(0)
  })

  it('produces query + phase nodes + edge for a single phase with no tacticians', () => {
    const run = makeRun({
      phases: {
        extract: { status: 'passed', n_tacticians: 0, distinct_candidate_names: [], gate_status: 'pass' },
      },
    })
    const g = buildDagFromRun(run)

    const kinds = g.nodes.map(n => n.data.kind)
    expect(kinds).toContain('query')
    expect(kinds).toContain('phase')
    expect(g.edges).toHaveLength(1)
    expect(g.edges[0].sourceId).toBe('node__query')
    expect(g.edges[0].targetId).toBe('node__phase__extract')
  })

  it('produces tactician nodes and phase→tactician edges', () => {
    const run = makeRun({
      phases: {
        extract: { status: 'running', n_tacticians: 2, distinct_candidate_names: [], gate_status: null },
      },
      tacticians: {
        extract: {
          0: { tactic_id: 't1', forbidden_candidates: [], candidate_names: ['Alice'], findings_count: 0, specialist_calls: 0 },
          1: { tactic_id: 't2', forbidden_candidates: ['Bob'], candidate_names: [], findings_count: 0, specialist_calls: 0 },
        },
      },
    })
    const g = buildDagFromRun(run)

    const tacNodes = g.nodes.filter(n => n.data.kind === 'tactician')
    expect(tacNodes).toHaveLength(2)

    const phaseEdges = g.edges.filter(e => e.sourceId === 'node__phase__extract')
    expect(phaseEdges).toHaveLength(2)
  })

  it('caps finding nodes at MAX_FINDINGS_PER_TACTICIAN', () => {
    const run = makeRun({
      phases: {
        extract: { status: 'running', n_tacticians: 1, distinct_candidate_names: [], gate_status: null },
      },
      tacticians: {
        extract: {
          0: {
            tactic_id: 't1',
            forbidden_candidates: [],
            candidate_names: [],
            findings_count: MAX_FINDINGS_PER_TACTICIAN + 5, // way above cap
            specialist_calls: 0,
          },
        },
      },
    })
    const g = buildDagFromRun(run)

    const findingNodes = g.nodes.filter(n => n.data.kind === 'finding')
    expect(findingNodes).toHaveLength(MAX_FINDINGS_PER_TACTICIAN)
  })

  it('produces no finding nodes when findings_count is 0', () => {
    const run = makeRun({
      phases: {
        extract: { status: 'running', n_tacticians: 1, distinct_candidate_names: [], gate_status: null },
      },
      tacticians: {
        extract: {
          0: { tactic_id: 't1', forbidden_candidates: [], candidate_names: [], findings_count: 0, specialist_calls: 0 },
        },
      },
    })
    const g = buildDagFromRun(run)
    const findingNodes = g.nodes.filter(n => n.data.kind === 'finding')
    expect(findingNodes).toHaveLength(0)
  })

  it('produces top-3 candidate nodes from rankedCandidates', () => {
    const run = makeRun({
      phases: {
        synthesize: { status: 'passed', n_tacticians: 0, distinct_candidate_names: [], gate_status: 'pass' },
      },
      rankedCandidates: [
        { name: 'Alice', confidence: 0.87, signal_scores: {}, evidence: [], slot_idx: 0 },
        { name: 'Bob', confidence: 0.64, signal_scores: {}, evidence: [], slot_idx: 1 },
        { name: 'Carol', confidence: 0.41, signal_scores: {}, evidence: [], slot_idx: 2 },
        { name: 'Dave', confidence: 0.20, signal_scores: {}, evidence: [], slot_idx: 3 }, // 4th — should be excluded
      ],
    })
    const g = buildDagFromRun(run)

    const candidateNodes = g.nodes.filter(n => n.data.kind === 'candidate')
    expect(candidateNodes).toHaveLength(3)

    const names = candidateNodes.map(n => n.data.kind === 'candidate' ? n.data.name : '')
    expect(names).toContain('Alice')
    expect(names).toContain('Bob')
    expect(names).toContain('Carol')
    expect(names).not.toContain('Dave')
  })

  it('places all nodes at non-negative x and y coordinates', () => {
    const run = makeRun({
      phases: {
        extract: { status: 'passed', n_tacticians: 2, distinct_candidate_names: [], gate_status: 'pass' },
        gather: { status: 'running', n_tacticians: 1, distinct_candidate_names: [], gate_status: null },
      },
      tacticians: {
        extract: {
          0: { tactic_id: 't1', forbidden_candidates: [], candidate_names: ['A'], findings_count: 2, specialist_calls: 0 },
          1: { tactic_id: 't2', forbidden_candidates: [], candidate_names: ['B'], findings_count: 1, specialist_calls: 0 },
        },
        gather: {
          0: { tactic_id: 't3', forbidden_candidates: [], candidate_names: [], findings_count: 0, specialist_calls: 0 },
        },
      },
    })
    const g = buildDagFromRun(run)

    for (const node of g.nodes) {
      expect(node.x).toBeGreaterThanOrEqual(0)
      expect(node.y).toBeGreaterThanOrEqual(0)
    }
  })

  it('does not produce edges past phase 1 when only 1 phase exists', () => {
    const run = makeRun({
      phases: {
        extract: { status: 'running', n_tacticians: 0, distinct_candidate_names: [], gate_status: null },
      },
    })
    const g = buildDagFromRun(run)

    // Only edge should be query → extract
    const nonQueryEdges = g.edges.filter(e => e.sourceId !== 'node__query')
    expect(nonQueryEdges).toHaveLength(0)
  })

  it('chains phase → phase edges for multiple phases', () => {
    const run = makeRun({
      phases: {
        extract: { status: 'passed', n_tacticians: 0, distinct_candidate_names: [], gate_status: 'pass' },
        gather: { status: 'running', n_tacticians: 0, distinct_candidate_names: [], gate_status: null },
      },
    })
    const g = buildDagFromRun(run)

    const p1ToP2 = g.edges.find(
      e => e.sourceId === 'node__phase__extract' && e.targetId === 'node__phase__gather'
    )
    expect(p1ToP2).toBeDefined()
  })

  it('assigns consistent source_class round-robin for synthetic finding nodes', () => {
    const run = makeRun({
      phases: {
        extract: { status: 'running', n_tacticians: 1, distinct_candidate_names: [], gate_status: null },
      },
      tacticians: {
        extract: {
          0: { tactic_id: 't1', forbidden_candidates: [], candidate_names: [], findings_count: 3, specialist_calls: 0 },
        },
      },
    })
    const g = buildDagFromRun(run)
    const findingNodes = g.nodes.filter(n => n.data.kind === 'finding')

    expect(findingNodes).toHaveLength(3)
    // All should have a non-null sourceClass
    for (const fn of findingNodes) {
      if (fn.data.kind === 'finding') {
        expect(fn.data.sourceClass).not.toBeNull()
      }
    }
  })
})
