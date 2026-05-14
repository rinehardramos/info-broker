/**
 * ResearchFlow — live visualization of the intelligent search agentic loop.
 *
 * Subscribes to WebSocket events and renders a tree of tool calls as an SVG DAG
 * that updates in real-time.
 *
 * Supports the PIR-bounded INVESTIGATE cycle:
 *   IS BRAIN → PIR node → Hypothesis nodes → Search/tool nodes
 */

import { useState, useCallback, useMemo, useEffect } from 'react'
import { useWebSocket, WsEvent } from '../../hooks/useWebSocket'
import { useChatStore } from '../../stores/chatStore'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface FlowNode {
  id: string            // call_id from backend
  tool: string          // tool name (e.g., "web_search")
  nodeType: 'pir' | 'hypothesis' | 'tool'
  params: Record<string, unknown>
  status: 'running' | 'succeeded' | 'failed'
  resultCount?: number
  resultPreview?: string
  queryPreview?: string
  parentId: string | null
  depth: number
  timestamp: number
  // PIR node fields
  pir?: string
  cycleId?: string
  parentCycleId?: string
  // Hypothesis node fields
  hypothesisIndex?: number
  hypothesisText?: string
}

interface FlowState {
  runId: string
  query: string
  nodes: FlowNode[]
  callCount: number
  maxCalls: number
  status: 'idle' | 'running' | 'succeeded' | 'failed'
  // Track latest cycle for hypothesis assignment
  latestCycleId?: string
  latestCyclePirNodeId?: string
  hypothesisNodeIds?: string[]   // ordered list of hypothesis node IDs for current cycle
  nextHypothesisIdx?: number     // which hypothesis to assign next search to
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

// Base sizes — scale down as node count grows
const _BASE_NODE_W = 140
const _BASE_NODE_H = 48
const _BASE_GAP_X = 40
const _BASE_GAP_Y = 12
const _BASE_ROOT_W = 90
const _BASE_ROOT_H = 36

function getScale(nodeCount: number) {
  if (nodeCount <= 5) return 1
  if (nodeCount <= 15) return 0.75
  if (nodeCount <= 30) return 0.55
  return 0.4
}

// These are recalculated per-render via useMemo, but we keep module-level defaults for non-flow code
let NODE_W = _BASE_NODE_W
let NODE_H = _BASE_NODE_H
let GAP_X = _BASE_GAP_X
let GAP_Y = _BASE_GAP_Y
let ROOT_W = _BASE_ROOT_W
let ROOT_H = _BASE_ROOT_H

const TOOL_COLORS: Record<string, string> = {
  // Search tools (blue)
  run_ddg_search:         '#60a5fa',
  run_web_search_fetch:   '#60a5fa',
  run_web_search:         '#60a5fa',
  run_google_news:        '#60a5fa',
  get_past_research:      '#60a5fa',
  search_obsidian:        '#60a5fa',
  run_qdrant_search:      '#60a5fa',
  run_serper_search:      '#60a5fa',
  run_tmdb_search:        '#60a5fa',
  run_multi_search:       '#60a5fa',
  // Crawl/fetch tools (purple)
  run_web_crawl:          '#a78bfa',
  run_headless_crawler:   '#a78bfa',
  run_wikipedia_api:      '#a78bfa',
  // People/B2B tools (pink)
  run_linkedin_profile_search: '#f472b6',
  run_linkedin_lookup:    '#f472b6',
  run_apollo_search:      '#f472b6',
  run_hunter_io:          '#f472b6',
  // Registry/OSINT tools (cyan)
  run_ph_sec_dti:         '#22d3ee',
  run_opencorporates:     '#22d3ee',
  run_ph_bir:             '#22d3ee',
  run_whois_lookup:       '#22d3ee',
  run_shodan_search:      '#22d3ee',
  // Social tools (orange)
  run_facebook_pages:     '#fb923c',
  run_twitter_search:     '#fb923c',
  run_instagram_profile:  '#fb923c',
  // Analysis tools (green)
  run_ai_scoring:         '#4ade80',
  run_summarizer:         '#4ade80',
  run_analyzer:           '#4ade80',
  // Meta tools (red)
  suggest_plugin:         '#f87171',
  run_clutch_goodfirms:   '#fb923c',
  run_clutch_buyer:       '#fb923c',
}

const STATUS_COLORS: Record<string, string> = {
  running:   '#facc15',
  succeeded: '#4ade80',
  failed:    '#f87171',
}

const HYPOTHESIS_COLORS = ['#60a5fa', '#a78bfa', '#4ade80', '#f87171', '#fb923c']
const PIR_COLOR = '#f59e0b'

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

// Module-level cache survives component unmount/remount
const _flowCache = new Map<string, FlowState>()

interface ExtraEdge {
  from: string
  to: string
  kind: 'result' | 'injected'
}

interface Props {
  /** If provided, only show flow for this run. Otherwise show latest. */
  runId?: string
  compact?: boolean
  extraEdges?: ExtraEdge[]
}

export function ResearchFlow({ runId: filterRunId, compact = false, extraEdges }: Props) {
  const sessionRunIds = useChatStore(s => s.sessionRunIds)
  const [flows, _setFlows] = useState<Map<string, FlowState>>(() => new Map(_flowCache))

  // When the session is cleared (sessionRunIds becomes empty), evict old flows from cache
  useEffect(() => {
    if (sessionRunIds.length === 0) {
      _flowCache.clear()
      _setFlows(new Map())
    }
  }, [sessionRunIds.length])
  // Wrapper that updates both state and cache
  const setFlows = (updater: (prev: Map<string, FlowState>) => Map<string, FlowState>) => {
    _setFlows(prev => {
      const next = updater(prev)
      // Sync cache
      for (const [k, v] of next) _flowCache.set(k, v)
      return next
    })
  }

  const handleEvent = useCallback((event: WsEvent) => {
    if (event.type === 'intelligent_search.started' && event.run_id) {
      setFlows(prev => {
        const next = new Map(prev)
        next.set(event.run_id!, {
          runId: event.run_id!,
          query: event.query ?? '',
          nodes: [],
          callCount: 0,
          maxCalls: event.max_calls ?? 20,
          status: 'running',
        })
        return next
      })
    }

    if (event.type === 'intelligent_search.tool_call' && event.run_id && event.call_id) {
      setFlows(prev => {
        const next = new Map(prev)
        const flow = next.get(event.run_id!) ?? {
          runId: event.run_id!, query: '', nodes: [],
          callCount: 0, maxCalls: event.max_calls ?? 20, status: 'running' as const,
        }
        // Avoid duplicate nodes
        if (flow.nodes.some(n => n.id === event.call_id)) return prev
        const node: FlowNode = {
          id: event.call_id!,
          tool: event.tool ?? 'unknown',
          nodeType: 'tool',
          params: event.params ?? {},
          status: 'running',
          parentId: event.parent_call_id ?? null,
          depth: event.depth ?? 1,
          timestamp: Date.now(),
        }
        next.set(event.run_id!, {
          ...flow,
          nodes: [...flow.nodes, node],
          callCount: event.call_count ?? flow.callCount + 1,
          maxCalls: event.max_calls ?? flow.maxCalls,
        })
        return next
      })
    }

    if (event.type === 'intelligent_search.tool_result' && event.run_id && event.call_id) {
      setFlows(prev => {
        const next = new Map(prev)
        const flow = next.get(event.run_id!)
        if (!flow) return prev
        next.set(event.run_id!, {
          ...flow,
          nodes: flow.nodes.map(n =>
            n.id === event.call_id
              ? {
                  ...n,
                  status: (event.status as FlowNode['status']) ?? 'succeeded',
                  resultCount: event.result_count,
                  resultPreview: event.result_preview,
                }
              : n
          ),
        })
        return next
      })
    }

    // IS cycle events — PIR-bounded INVESTIGATE cycle declaration
    if (event.type === 'is.cycle' && event.run_id) {
      setFlows(prev => {
        const next = new Map(prev)
        const flow = next.get(event.run_id!) ?? {
          runId: event.run_id!, query: '', nodes: [],
          callCount: 0, maxCalls: 50, status: 'running' as const,
        }

        // Find parent node — parent cycle's PIR node, or BRAIN (null)
        const parentPirNodeId = event.parent_cycle_id
          ? flow.nodes.find(n => n.nodeType === 'pir' && n.cycleId === event.parent_cycle_id)?.id ?? null
          : null

        // Create PIR node
        const pirNodeId = `pir_${event.call_id || event.cycle_id}`
        const pirNode: FlowNode = {
          id: pirNodeId,
          tool: 'pir',
          nodeType: 'pir',
          params: {},
          status: 'running',
          parentId: parentPirNodeId,
          depth: 0,
          timestamp: Date.now(),
          pir: event.pir ?? '',
          cycleId: event.cycle_id ?? '',
          parentCycleId: event.parent_cycle_id ?? '',
        }

        // Create hypothesis nodes, each parented to the PIR node
        const hypotheses: string[] = event.hypotheses ?? []
        const hypothesisNodes: FlowNode[] = hypotheses.map((h, i) => ({
          id: `hyp_${event.call_id || event.cycle_id}_${i}`,
          tool: 'hypothesis',
          nodeType: 'hypothesis' as const,
          params: {},
          status: 'running' as const,
          parentId: pirNodeId,
          depth: 1,
          timestamp: Date.now(),
          hypothesisIndex: i,
          hypothesisText: h,
        }))

        const hypothesisNodeIds = hypothesisNodes.map(n => n.id)

        next.set(event.run_id!, {
          ...flow,
          nodes: [...flow.nodes, pirNode, ...hypothesisNodes],
          latestCycleId: event.cycle_id ?? '',
          latestCyclePirNodeId: pirNodeId,
          hypothesisNodeIds,
          nextHypothesisIdx: 0,
        })
        return next
      })
    }

    // IS brain events (from Claude Code subprocess — is.tool_call / is.tool_result)
    if (event.type === 'is.tool_call' && event.run_id && event.call_id) {
      setFlows(prev => {
        const next = new Map(prev)
        const flow = next.get(event.run_id!) ?? {
          runId: event.run_id!, query: '', nodes: [],
          callCount: 0, maxCalls: 50, status: 'running' as const,
        }
        if (flow.nodes.some(n => n.id === event.call_id)) return prev

        const tool = event.tool ?? 'unknown'
        const searchTools = ['run_ddg_search', 'run_web_search_fetch', 'run_web_search', 'run_google_news', 'get_past_research', 'search_obsidian', 'run_qdrant_search', 'run_serper_search', 'run_tmdb_search', 'run_multi_search']
        const isSearchTool = searchTools.includes(tool)

        // Assign BROADEN search nodes to hypothesis parents (round-robin by sequence)
        let parentId: string | null = null
        let depth = 2
        let nextHypothesisIdx = flow.nextHypothesisIdx ?? 0

        if (isSearchTool && flow.hypothesisNodeIds && flow.hypothesisNodeIds.length > 0) {
          const assignIdx = nextHypothesisIdx % flow.hypothesisNodeIds.length
          parentId = flow.hypothesisNodeIds[assignIdx]
          depth = 2
          nextHypothesisIdx = nextHypothesisIdx + 1
        } else if (flow.latestCyclePirNodeId) {
          // Non-search tools (crawl, person lookup, analysis) link to PIR
          parentId = flow.latestCyclePirNodeId
          const enrichTools = ['run_web_crawl', 'run_headless_crawler', 'run_wikipedia_api', 'run_ph_sec_dti', 'run_opencorporates', 'run_whois_lookup', 'run_facebook_pages', 'run_twitter_search', 'run_instagram_profile', 'run_shodan_search']
          const personTools = ['run_linkedin_profile_search', 'run_linkedin_lookup', 'run_apollo_search', 'run_hunter_io', 'run_clutch_goodfirms', 'run_clutch_buyer']
          const analysisTools = ['run_ai_scoring', 'run_summarizer', 'run_analyzer', 'suggest_plugin']
          if (enrichTools.includes(tool)) depth = 3
          else if (personTools.includes(tool)) depth = 3
          else if (analysisTools.includes(tool)) depth = 4
        } else {
          // Fallback: no cycle declared yet, use old depth inference
          const enrichTools = ['run_web_crawl', 'run_headless_crawler', 'run_wikipedia_api']
          const personTools = ['run_linkedin_profile_search', 'run_linkedin_lookup', 'run_apollo_search', 'run_hunter_io']
          const analysisTools = ['run_ai_scoring', 'run_summarizer', 'run_analyzer', 'suggest_plugin']
          if (enrichTools.includes(tool)) depth = 2
          else if (personTools.includes(tool)) depth = 3
          else if (analysisTools.includes(tool)) depth = 4
          else depth = 1
        }

        const node: FlowNode = {
          id: event.call_id!,
          tool,
          nodeType: 'tool',
          params: {},
          status: event.status === 'calling' ? 'running' : (event.status as FlowNode['status'] ?? 'running'),
          parentId,
          depth,
          timestamp: Date.now(),
          queryPreview: event.query_preview ?? '',
        }
        next.set(event.run_id!, {
          ...flow,
          nodes: [...flow.nodes, node],
          callCount: flow.callCount + 1,
          nextHypothesisIdx,
        })
        return next
      })
    }

    if (event.type === 'is.tool_result' && event.run_id && event.call_id) {
      setFlows(prev => {
        const next = new Map(prev)
        const flow = next.get(event.run_id!)
        if (!flow) return prev
        next.set(event.run_id!, {
          ...flow,
          nodes: flow.nodes.map(n =>
            n.id === event.call_id
              ? { ...n, status: 'succeeded' as const, resultPreview: event.preview ?? event.result_preview }
              : n
          ),
        })
        return next
      })
    }

    // Mark IS run complete — also mark all PIR nodes as succeeded
    if ((event.type === 'job.completed' || event.type === 'job.failed') && event.run_id) {
      setFlows(prev => {
        const next = new Map(prev)
        const flow = next.get(event.run_id!)
        if (!flow) return prev
        const finalStatus: FlowNode['status'] = event.type === 'job.completed' ? 'succeeded' : 'failed'
        next.set(event.run_id!, {
          ...flow,
          status: event.type === 'job.completed' ? 'succeeded' : 'failed',
          nodes: flow.nodes.map(n =>
            n.nodeType === 'pir' && n.status === 'running'
              ? { ...n, status: finalStatus }
              : n
          ),
        })
        return next
      })
    }

    if (event.type === 'pipeline.step.update' && event.run_id && event.status) {
      if (event.status === 'succeeded' || event.status === 'failed') {
        setFlows(prev => {
          const next = new Map(prev)
          const flow = next.get(event.run_id!)
          if (!flow || flow.status !== 'running') return prev
          next.set(event.run_id!, { ...flow, status: event.status as FlowState['status'] })
          return next
        })
      }
    }
  }, [])

  useWebSocket(handleEvent)

  // Pick which flow to display — scoped to current session runs
  const activeFlow = useMemo(() => {
    if (filterRunId) return flows.get(filterRunId)
    // Only consider flows that belong to the current session
    const sessionSet = new Set(sessionRunIds)
    const all = [...flows.values()].filter(f => sessionSet.size === 0 || sessionSet.has(f.runId))
    return all.find(f => f.status === 'running') ?? all[all.length - 1]
  }, [flows, filterRunId, sessionRunIds])

  if (!activeFlow || activeFlow.nodes.length === 0) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#475569', gap: 8 }}>
        <span style={{ fontSize: 24 }}>&#x1F50D;</span>
        <span style={{ fontSize: 12 }}>No active research</span>
        <span style={{ fontSize: 10, color: '#334155' }}>
          Run a pipeline with Intelligent Search to see the live flow graph
        </span>
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      {/* Header */}
      <div style={{ padding: '8px 12px', borderBottom: '1px solid #1e293b', flexShrink: 0 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontSize: 11, fontWeight: 700, color: '#e2e8f0' }}>
            {activeFlow.status === 'running' ? '⚡' : '✅'}{' '}
            {activeFlow.query ? `"${activeFlow.query.slice(0, 60)}"` : 'Research'}
          </span>
          <span style={{
            fontSize: 9,
            color: STATUS_COLORS[activeFlow.status] ?? '#94a3b8',
            fontWeight: 600,
          }}>
            {activeFlow.status.toUpperCase()}
          </span>
        </div>
        {/* Progress bar */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 4 }}>
          <div style={{ flex: 1, height: 4, background: '#1e293b', borderRadius: 2, overflow: 'hidden' }}>
            <div style={{
              height: '100%',
              // Once the run is terminal, the bar represents completion (100%),
              // not the literal callCount/maxCalls ratio.
              width: activeFlow.status === 'running'
                ? `${Math.min(100, (activeFlow.callCount / activeFlow.maxCalls) * 100)}%`
                : '100%',
              background: activeFlow.status === 'running' ? '#facc15' : '#4ade80',
              borderRadius: 2,
              transition: 'width 0.3s ease',
            }} />
          </div>
          <span style={{ fontSize: 9, color: '#64748b', flexShrink: 0 }}>
            {activeFlow.callCount}/{activeFlow.maxCalls} calls
          </span>
        </div>
      </div>

      {/* Flow graph */}
      <div style={{ flex: 1, overflow: 'auto', padding: 8 }}>
        <FlowGraph nodes={activeFlow.nodes} query={activeFlow.query} compact={compact} extraEdges={extraEdges} />
      </div>
    </div>
  )
}


// ---------------------------------------------------------------------------
// SVG Flow Graph
// ---------------------------------------------------------------------------

function FlowGraph({ nodes, query, compact = false, extraEdges }: { nodes: FlowNode[]; query: string; compact?: boolean; extraEdges?: ExtraEdge[] }) {
  // Dynamic sizing based on node count; compact mode applies an additional 0.6x scale
  const s = getScale(nodes.length) * (compact ? 0.6 : 1)
  const nw = Math.round(_BASE_NODE_W * s)
  const nh = Math.round(_BASE_NODE_H * s)
  const gx = Math.round(_BASE_GAP_X * s)
  const gy = Math.round(_BASE_GAP_Y * s)
  const rw = Math.round(_BASE_ROOT_W * s)
  const rh = Math.round(_BASE_ROOT_H * s)
  const fontSize = Math.max(7, Math.round(9 * s))
  const fontSizeSm = Math.max(6, Math.round(8 * s))

  // Update module-level vars so edge calculations use correct sizes
  NODE_W = nw; NODE_H = nh; GAP_X = gx; GAP_Y = gy; ROOT_W = rw; ROOT_H = rh

  // PIR nodes are wider than regular nodes
  const pirW = Math.round(nw * 1.3)

  // Uniform column width — wide enough for any node type
  const COL_W = Math.round(Math.max(nw, pirW) + gx)

  // Leaf row height — vertical spacing per leaf
  const LEAF_H = nh + gy

  const rootX = 12
  const rootY = 12

  // ---------------------------------------------------------------------------
  // Step 1: Build tree structure from nodes
  // ---------------------------------------------------------------------------
  const childrenMap: Record<string, string[]> = { brain: [] }
  const nodeById: Record<string, FlowNode> = {}

  for (const node of nodes) {
    nodeById[node.id] = node
    const parentKey = node.parentId ?? 'brain'
    if (!childrenMap[parentKey]) childrenMap[parentKey] = []
    childrenMap[parentKey].push(node.id)
    if (!childrenMap[node.id]) childrenMap[node.id] = []
  }

  // ---------------------------------------------------------------------------
  // Step 2: Count leaf nodes in subtree (memoized)
  // ---------------------------------------------------------------------------
  const leafCountCache: Record<string, number> = {}
  function countLeaves(id: string): number {
    if (leafCountCache[id] !== undefined) return leafCountCache[id]
    const kids = childrenMap[id] ?? []
    const result = kids.length === 0 ? 1 : kids.reduce((sum, kid) => sum + countLeaves(kid), 0)
    leafCountCache[id] = result
    return result
  }

  // ---------------------------------------------------------------------------
  // Step 3: Assign positions recursively
  // ---------------------------------------------------------------------------
  const positions: Record<string, { x: number; y: number }> = {}

  function layout(id: string, col: number, yStart: number): void {
    const kids = childrenMap[id] ?? []
    const leafCount = countLeaves(id)
    const totalH = leafCount * LEAF_H - gy

    if (id === 'brain') {
      positions.brain = { x: rootX, y: yStart + Math.max(0, (totalH - rh) / 2) }
    } else {
      const nodeX = rootX + rw + gx + (col - 1) * COL_W
      positions[id] = { x: nodeX, y: yStart + Math.max(0, (totalH - nh) / 2) }
    }

    let childY = yStart
    for (const kidId of kids) {
      const kidLeaves = countLeaves(kidId)
      layout(kidId, col + 1, childY)
      childY += kidLeaves * LEAF_H
    }
  }

  layout('brain', 0, rootY)

  // ---------------------------------------------------------------------------
  // Step 4: Compute SVG dimensions from actual positions
  // ---------------------------------------------------------------------------
  const allPositions = Object.values(positions)
  const svgW = Math.max(...allPositions.map(p => p.x + COL_W)) + 16
  const svgH = Math.max(...allPositions.map(p => p.y + nh)) + 16

  // ---------------------------------------------------------------------------
  // Step 5: Edge helpers — use actual tree positions
  // ---------------------------------------------------------------------------
  function getNodeRight(id: string | null): number {
    if (!id || id === 'brain') return (positions.brain?.x ?? rootX) + rw
    const pos = positions[id]
    const node = nodeById[id]
    if (!pos || !node) return (positions.brain?.x ?? rootX) + rw
    if (node.nodeType === 'pir') return pos.x + pirW
    return pos.x + nw
  }

  function getNodeMidY(id: string | null): number {
    if (!id || id === 'brain') return (positions.brain?.y ?? rootY) + rh / 2
    const pos = positions[id]
    const node = nodeById[id]
    if (!pos || !node) return rootY + rh / 2
    if (node.nodeType === 'pir') {
      const pirH = Math.round(nh * 1.5)
      const pirYAdjusted = pos.y - (pirH - nh) / 2
      return pirYAdjusted + pirH / 2
    }
    return pos.y + nh / 2
  }

  return (
    <svg
      width="100%"
      height="100%"
      viewBox={`0 0 ${svgW} ${svgH}`}
      preserveAspectRatio="xMidYMid meet"
      style={{
        background: '#0a0e14',
        borderRadius: 6,
        minHeight: 200,
      }}
      pointerEvents={compact ? 'none' : undefined}
    >
      <defs>
        <marker id="flow-arrow" markerWidth="6" markerHeight="6" refX="6" refY="3" orient="auto">
          <path d="M0,0 L6,3 L0,6 Z" fill="#475569" opacity={0.8} />
        </marker>
        <marker id="flow-arrow-active" markerWidth="6" markerHeight="6" refX="6" refY="3" orient="auto">
          <path d="M0,0 L6,3 L0,6 Z" fill="#facc15" opacity={0.9} />
        </marker>
        <marker id="flow-arrow-pir" markerWidth="6" markerHeight="6" refX="6" refY="3" orient="auto">
          <path d="M0,0 L6,3 L0,6 Z" fill={PIR_COLOR} opacity={0.9} />
        </marker>
      </defs>

      {/* Edges */}
      {nodes.map(node => {
        const parentPos = node.parentId ? positions[node.parentId] : positions['brain']
        const childPos = positions[node.id]
        if (!parentPos || !childPos) return null

        const x1 = getNodeRight(node.parentId)
        const y1 = getNodeMidY(node.parentId)
        const x2 = childPos.x
        const y2 = childPos.y + nh / 2
        const isRunning = node.status === 'running'
        const isPirEdge = node.nodeType === 'pir'
        const isHypEdge = node.nodeType === 'hypothesis'
        const hColor = isHypEdge
          ? HYPOTHESIS_COLORS[(node.hypothesisIndex ?? 0) % HYPOTHESIS_COLORS.length]
          : undefined

        return (
          <path
            key={`edge-${node.id}`}
            d={`M${x1},${y1} C${x1 + (x2 - x1) * 0.5},${y1} ${x1 + (x2 - x1) * 0.5},${y2} ${x2},${y2}`}
            fill="none"
            stroke={isPirEdge ? PIR_COLOR : isHypEdge ? hColor! : (isRunning ? '#facc15' : '#475569')}
            strokeWidth={isPirEdge ? 2 : 1.5}
            strokeDasharray={isRunning && !isPirEdge ? '4 3' : undefined}
            opacity={0.7}
            markerEnd={isPirEdge ? 'url(#flow-arrow-pir)' : isRunning ? 'url(#flow-arrow-active)' : 'url(#flow-arrow)'}
          />
        )
      })}

      {/* Brain root node */}
      {(() => {
        const pos = positions['brain']
        return (
          <g>
            <rect x={pos.x} y={pos.y} width={rw} height={rh} rx={rh / 2} fill="#1e293b" stroke="#a78bfa" strokeWidth={1.5} />
            {!compact && (
              <>
                <text x={pos.x + rw / 2} y={pos.y + rh * 0.4} textAnchor="middle" fill="#a78bfa" fontSize={fontSize} fontWeight={700}>IS BRAIN</text>
                <text x={pos.x + rw / 2} y={pos.y + rh * 0.72} textAnchor="middle" fill="#94a3b8" fontSize={fontSizeSm}>
                  {query.slice(0, Math.round(14 * s))}{query.length > Math.round(14 * s) ? '...' : ''}
                </text>
              </>
            )}
          </g>
        )
      })()}

      {/* Tool call nodes */}
      {nodes.map(node => {
        const pos = positions[node.id]
        if (!pos) return null

        // PIR node — amber/orange, wider, shows PIR question
        if (node.nodeType === 'pir') {
          const statusColor = STATUS_COLORS[node.status] ?? '#475569'
          const pirText = node.pir ?? ''
          const pirH = Math.round(nh * 1.5)  // Taller to fit 3 lines
          const pirYAdjusted = pos.y - (pirH - nh) / 2  // Center vertically relative to original pos
          const charsPerLine = Math.max(10, Math.floor(pirW / (fontSize * 0.58)))
          const line1 = pirText.slice(0, charsPerLine)
          const line2 = pirText.length > charsPerLine ? pirText.slice(charsPerLine, charsPerLine * 2) : ''

          return (
            <g key={node.id}>
              <title>{pirText}</title>
              <rect
                x={pos.x} y={pirYAdjusted}
                width={pirW} height={pirH}
                rx={6}
                fill="#1c1a0e"
                stroke={node.status === 'running' ? '#facc15' : PIR_COLOR}
                strokeWidth={2}
              />
              {!compact && (
                <>
                  <text x={pos.x + 6} y={pirYAdjusted + pirH * 0.25} fill={PIR_COLOR} fontSize={fontSize} fontWeight={700}>
                    PIR
                  </text>
                  <text x={pos.x + 6} y={pirYAdjusted + pirH * 0.48} fill="#fcd34d" fontSize={fontSizeSm}>
                    {line1}
                  </text>
                  {line2 && (
                    <text x={pos.x + 6} y={pirYAdjusted + pirH * 0.70} fill="#fcd34d" fontSize={fontSizeSm}>
                      {line2}
                    </text>
                  )}
                  <text x={pos.x + 6} y={pirYAdjusted + pirH * 0.90} fill={statusColor} fontSize={fontSizeSm} fontWeight={600}>
                    {node.status === 'running' ? '⏳ investigating...' : node.status === 'succeeded' ? '✓ done' : '✗ failed'}
                  </text>
                </>
              )}
            </g>
          )
        }

        // Hypothesis node — colored by index
        if (node.nodeType === 'hypothesis') {
          const hColor = HYPOTHESIS_COLORS[(node.hypothesisIndex ?? 0) % HYPOTHESIS_COLORS.length]
          const hypText = node.hypothesisText ?? ''
          const charsPerLine = Math.max(10, Math.floor(nw / (fontSize * 0.58)))
          const line1 = hypText.slice(0, charsPerLine)
          const line2 = hypText.length > charsPerLine ? hypText.slice(charsPerLine, charsPerLine * 2) : ''

          return (
            <g key={node.id}>
              <title>{hypText}</title>
              <rect
                x={pos.x} y={pos.y}
                width={nw} height={nh}
                rx={4}
                fill="#0f172a"
                stroke={hColor}
                strokeWidth={1.5}
              />
              {!compact && (
                <>
                  <text x={pos.x + 6} y={pos.y + nh * 0.3} fill={hColor} fontSize={fontSize} fontWeight={600}>
                    H{(node.hypothesisIndex ?? 0) + 1}
                  </text>
                  <text x={pos.x + 6} y={pos.y + nh * 0.50} fill="#94a3b8" fontSize={fontSizeSm}>
                    {line1}
                  </text>
                  {line2 && (
                    <text x={pos.x + 6} y={pos.y + nh * 0.72} fill="#94a3b8" fontSize={fontSizeSm}>
                      {line2}
                    </text>
                  )}
                </>
              )}
            </g>
          )
        }

        // Generic tool node
        const color = TOOL_COLORS[node.tool] ?? '#60a5fa'
        const statusColor = STATUS_COLORS[node.status] ?? '#475569'
        // Build human-readable description from tool + query
        const descText = (() => {
          const q = node.queryPreview ?? ''
          if (!q) return ''
          // Normalize: lowercase + strip underscores so WebSearch == web_search
          const t = node.tool.toLowerCase().replace(/_/g, '')
          if (t.includes('websearch') || t.includes('ddgsearch') || t.includes('toolsearch') ||
              t.includes('serpersearch') || t.includes('qdrantsearch') || t.includes('multisearch')) return `Searching: ${q}`
          if (t.includes('crawl') || t.includes('headless') || t.includes('fetch')) return `Crawling: ${q.replace(/^https?:\/\//, '').split('/')[0]}`
          if (t.includes('news') || t.includes('rss')) return `News: ${q}`
          if (t.includes('linkedin')) return `LinkedIn: ${q}`
          if (t.includes('apollo')) return `Apollo: ${q}`
          if (t.includes('tmdb')) return `TMDB: ${q}`
          if (t.includes('opencorporates') || t.includes('secdti') || t.includes('bir')) return `Registry: ${q}`
          if (t.includes('pastresearch') || t.includes('past_research')) return `Prior: ${q}`
          if (t.includes('wikipedia')) return `Wikipedia: ${q}`
          if (t.includes('hunter')) return `Hunter.io: ${q}`
          if (t.includes('shodan')) return `Shodan: ${q}`
          if (t.includes('linkedin')) return `LinkedIn: ${q}`
          return `Searching: ${q}`
        })()
        return (
          <g key={node.id}>
            <title>{`${node.tool}${descText ? `: ${descText}` : ''}${node.resultPreview ? ` → ${node.resultPreview}` : ''}`}</title>
            <rect
              x={pos.x} y={pos.y}
              width={nw} height={nh}
              rx={4}
              fill="#1e293b"
              stroke={node.status === 'running' ? '#facc15' : statusColor}
              strokeWidth={1}
            />
            {!compact && (
              <>
                {/* Tool name */}
                <text x={pos.x + 6} y={pos.y + nh * 0.3} fill={color} fontSize={fontSize} fontWeight={700}>
                  {node.tool.replace(/^run_/, '').replace(/_/g, ' ').slice(0, Math.round(18 * s))}
                </text>
                {/* Description preview (query/URL/name being searched) */}
                <text x={pos.x + 6} y={pos.y + nh * 0.55} fill="#94a3b8" fontSize={fontSizeSm}>
                  {descText.slice(0, Math.round(22 * s))}{descText.length > Math.round(22 * s) ? '…' : ''}
                </text>
                {/* Status + result count */}
                <text x={pos.x + 6} y={pos.y + nh * 0.82} fill={statusColor} fontSize={fontSizeSm} fontWeight={600}>
                  {node.status === 'running'
                    ? '⏳ running...'
                    : node.status === 'succeeded'
                      ? `✓ ${node.resultCount ?? 0} results`
                      : '✗ failed'}
                </text>
              </>
            )}
          </g>
        )
      })}

      {/* Extra edges — dashed violet overlay */}
      {extraEdges?.map((ee, i) => {
        const src = positions[ee.from]
        const tgt = positions[ee.to]
        if (!src || !tgt) return null
        const srcNode = nodeById[ee.from]
        const tgtNode = nodeById[ee.to]
        const x1 = src.x + (srcNode?.nodeType === 'pir' ? pirW : nw) / 2
        const y1 = src.y + nh / 2
        const x2 = tgt.x + (tgtNode?.nodeType === 'pir' ? pirW : nw) / 2
        const y2 = tgt.y + nh / 2
        return (
          <line
            key={`extra-${i}`}
            x1={x1} y1={y1}
            x2={x2} y2={y2}
            stroke="#7c3aed"
            strokeWidth={1.5}
            strokeDasharray="4,3"
          />
        )
      })}
    </svg>
  )
}
