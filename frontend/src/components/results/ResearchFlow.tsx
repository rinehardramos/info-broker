/**
 * ResearchFlow — live visualization of the intelligent search agentic loop.
 *
 * Subscribes to WebSocket events and renders a tree of tool calls as an SVG DAG
 * that updates in real-time.
 */

import { useState, useCallback, useMemo } from 'react'
import { useWebSocket, WsEvent } from '../../hooks/useWebSocket'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface FlowNode {
  id: string            // call_id from backend
  tool: string          // tool name (e.g., "web_search")
  params: Record<string, unknown>
  status: 'running' | 'succeeded' | 'failed'
  resultCount?: number
  resultPreview?: string
  parentId: string | null
  depth: number
  timestamp: number
}

interface FlowState {
  runId: string
  query: string
  nodes: FlowNode[]
  callCount: number
  maxCalls: number
  status: 'idle' | 'running' | 'succeeded' | 'failed'
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const NODE_W = 150
const NODE_H = 52
const GAP_X = 60
const GAP_Y = 16
const ROOT_W = 100
const ROOT_H = 40

const TOOL_COLORS: Record<string, string> = {
  web_search:       '#60a5fa',
  follow_url:       '#a78bfa',
  search_obsidian:  '#f472b6',
  search_files:     '#f472b6',
  web_crawl:        '#f472b6',
  mark_for_review:  '#fb923c',
  request_plugin:   '#f87171',
  finish_research:  '#4ade80',
}

const STATUS_COLORS: Record<string, string> = {
  running:   '#facc15',
  succeeded: '#4ade80',
  failed:    '#f87171',
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface Props {
  /** If provided, only show flow for this run. Otherwise show latest. */
  runId?: string
}

export function ResearchFlow({ runId: filterRunId }: Props) {
  const [flows, setFlows] = useState<Map<string, FlowState>>(new Map())

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

  // Pick which flow to display
  const activeFlow = useMemo(() => {
    if (filterRunId) return flows.get(filterRunId)
    // Show latest running, or latest overall
    const all = [...flows.values()]
    return all.find(f => f.status === 'running') ?? all[all.length - 1]
  }, [flows, filterRunId])

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
            {activeFlow.status === 'running' ? '\u26A1' : '\u2705'}{' '}
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
              width: `${Math.min(100, (activeFlow.callCount / activeFlow.maxCalls) * 100)}%`,
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
        <FlowGraph nodes={activeFlow.nodes} query={activeFlow.query} />
      </div>
    </div>
  )
}


// ---------------------------------------------------------------------------
// SVG Flow Graph
// ---------------------------------------------------------------------------

function FlowGraph({ nodes, query }: { nodes: FlowNode[]; query: string }) {
  // Build tree layout: group by depth, root "BRAIN" at left
  const byDepth: Record<number, FlowNode[]> = {}
  for (const n of nodes) {
    byDepth[n.depth] = byDepth[n.depth] ?? []
    byDepth[n.depth].push(n)
  }
  const depths = Object.keys(byDepth).map(Number).sort((a, b) => a - b)

  // Position root node
  const totalNodes = nodes.length
  const rootX = 16
  const rootY = 16

  // Position tool call nodes by depth column
  const positions: Record<string, { x: number; y: number }> = {}
  positions['brain'] = { x: rootX, y: rootY + Math.max(0, (totalNodes - 1) * (NODE_H + GAP_Y) / 2 - ROOT_H / 2) }

  depths.forEach((d, di) => {
    const layer = byDepth[d]
    layer.forEach((node, ni) => {
      positions[node.id] = {
        x: rootX + ROOT_W + GAP_X + di * (NODE_W + GAP_X),
        y: 16 + ni * (NODE_H + GAP_Y),
      }
    })
  })

  const maxX = Math.max(rootX + ROOT_W, ...Object.values(positions).map(p => p.x + NODE_W))
  const maxY = Math.max(rootY + ROOT_H, ...Object.values(positions).map(p => p.y + NODE_H))
  const svgW = maxX + 24
  const svgH = maxY + 24

  return (
    <svg width="100%" height="100%" viewBox={`0 0 ${svgW} ${svgH}`} style={{ background: '#0a0e14', borderRadius: 6, minHeight: 200 }}>
      <defs>
        <marker id="flow-arrow" markerWidth="6" markerHeight="6" refX="6" refY="3" orient="auto">
          <path d="M0,0 L6,3 L0,6 Z" fill="#475569" opacity={0.8} />
        </marker>
        <marker id="flow-arrow-active" markerWidth="6" markerHeight="6" refX="6" refY="3" orient="auto">
          <path d="M0,0 L6,3 L0,6 Z" fill="#facc15" opacity={0.9} />
        </marker>
      </defs>

      {/* Edges: brain → depth-1 nodes, parent → child */}
      {nodes.map(node => {
        const parentPos = node.parentId ? positions[node.parentId] : positions['brain']
        const childPos = positions[node.id]
        if (!parentPos || !childPos) return null
        const x1 = node.parentId ? parentPos.x + NODE_W : parentPos.x + ROOT_W
        const y1 = node.parentId ? parentPos.y + NODE_H / 2 : parentPos.y + ROOT_H / 2
        const x2 = childPos.x
        const y2 = childPos.y + NODE_H / 2
        const isRunning = node.status === 'running'
        return (
          <path
            key={`edge-${node.id}`}
            d={`M${x1},${y1} C${x1 + (x2 - x1) * 0.5},${y1} ${x1 + (x2 - x1) * 0.5},${y2} ${x2},${y2}`}
            fill="none"
            stroke={isRunning ? '#facc15' : '#475569'}
            strokeWidth={1.5}
            strokeDasharray={isRunning ? '4 3' : undefined}
            opacity={0.7}
            markerEnd={isRunning ? 'url(#flow-arrow-active)' : 'url(#flow-arrow)'}
          />
        )
      })}

      {/* Brain root node */}
      {(() => {
        const pos = positions['brain']
        return (
          <g>
            <rect x={pos.x} y={pos.y} width={ROOT_W} height={ROOT_H} rx={20} fill="#1e293b" stroke="#a78bfa" strokeWidth={2} />
            <text x={pos.x + ROOT_W / 2} y={pos.y + 16} textAnchor="middle" fill="#a78bfa" fontSize={9} fontWeight={700}>BRAIN</text>
            <text x={pos.x + ROOT_W / 2} y={pos.y + 28} textAnchor="middle" fill="#94a3b8" fontSize={8}>
              {query.slice(0, 14)}{query.length > 14 ? '...' : ''}
            </text>
          </g>
        )
      })()}

      {/* Tool call nodes */}
      {nodes.map(node => {
        const pos = positions[node.id]
        if (!pos) return null
        const color = TOOL_COLORS[node.tool] ?? '#60a5fa'
        const statusColor = STATUS_COLORS[node.status] ?? '#475569'
        const paramStr = Object.values(node.params).map(v => String(v).slice(0, 20)).join(', ')
        return (
          <g key={node.id}>
            <rect
              x={pos.x} y={pos.y}
              width={NODE_W} height={NODE_H}
              rx={6}
              fill="#1e293b"
              stroke={node.status === 'running' ? '#facc15' : statusColor}
              strokeWidth={1.5}
            />
            {/* Tool name */}
            <text x={pos.x + 8} y={pos.y + 14} fill={color} fontSize={9} fontWeight={700}>
              {node.tool}
            </text>
            {/* Params preview */}
            <text x={pos.x + 8} y={pos.y + 26} fill="#94a3b8" fontSize={8}>
              {paramStr.slice(0, 20)}{paramStr.length > 20 ? '...' : ''}
            </text>
            {/* Status + result count */}
            <text x={pos.x + 8} y={pos.y + 40} fill={statusColor} fontSize={8} fontWeight={600}>
              {node.status === 'running'
                ? '\u23F3 running...'
                : node.status === 'succeeded'
                  ? `\u2713 ${node.resultCount ?? 0} results`
                  : '\u2717 failed'}
            </text>
          </g>
        )
      })}
    </svg>
  )
}
