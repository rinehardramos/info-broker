import { PipelineNodeOut, PipelineEdgeOut, PipelineStepRun } from '../../api/pipelines'

const NODE_W = 160
const NODE_H = 60
const GAP_X = 80
const GAP_Y = 30
const SENTINEL_W = 64
const SENTINEL_H = 28
const SENTINEL_COLOR = '#475569'

const CATEGORY_COLORS: Record<string, string> = {
  source: '#60a5fa',
  enrich: '#a78bfa',
  score: '#4ade80',
  filter: '#fb923c',
  datastore: '#f472b6',
}

const STATUS_COLORS: Record<string, string> = {
  succeeded: '#4ade80',
  failed: '#f87171',
  running: '#facc15',
  pending: '#475569',
}

interface Props {
  nodes: PipelineNodeOut[]
  edges: PipelineEdgeOut[]
  stepRuns?: PipelineStepRun[]
}

function topoLayers(nodes: PipelineNodeOut[], edges: PipelineEdgeOut[]): PipelineNodeOut[][] {
  // Only results edges drive execution order; tool edges are rendered separately
  const resultEdges = edges.filter(e => (e as any).edge_type !== 'tool')
  const validIds = new Set(nodes.map(n => n.id))
  const deps: Record<string, Set<string>> = {}
  for (const n of nodes) deps[n.id] = new Set()
  for (const e of resultEdges) {
    // Only track deps for edges where both ends are valid nodes
    if (deps[e.target_node_id] && validIds.has(e.source_node_id)) {
      deps[e.target_node_id].add(e.source_node_id)
    }
  }

  const layers: PipelineNodeOut[][] = []
  const resolved = new Set<string>()

  while (resolved.size < nodes.length) {
    const layer = nodes.filter(
      n => !resolved.has(n.id) && [...deps[n.id]].every(d => resolved.has(d))
    )
    if (!layer.length) break
    layers.push(layer)
    layer.forEach(n => resolved.add(n.id))
  }

  // Any nodes not placed (cycles or completely disconnected) get a final layer
  const unplaced = nodes.filter(n => !resolved.has(n.id))
  if (unplaced.length) layers.push(unplaced)

  return layers
}

export function DagPreview({ nodes, edges, stepRuns = [] }: Props) {
  if (!nodes.length) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#475569' }}>
        Add nodes to see the graph
      </div>
    )
  }

  const stepMap = Object.fromEntries(stepRuns.map(s => [s.node_id, s]))
  const layers = topoLayers(nodes, edges)

  // Shift all real nodes right to make room for the START sentinel
  const X_OFFSET = SENTINEL_W + GAP_X

  // Compute positions
  const positions: Record<string, { x: number; y: number }> = {}
  let maxY = 0
  layers.forEach((layer, layerIdx) => {
    layer.forEach((node, nodeIdx) => {
      const x = 20 + X_OFFSET + layerIdx * (NODE_W + GAP_X)
      const y = 20 + nodeIdx * (NODE_H + GAP_Y)
      positions[node.id] = { x, y }
      maxY = Math.max(maxY, y + NODE_H)
    })
  })

  const svgHeight = maxY + 40

  // Sentinel positions — centered on their connected nodes (results edges only)
  const resultEdgesOnly = edges.filter(e => (e as any).edge_type !== 'tool')
  const incomingIds = new Set(resultEdgesOnly.map(e => e.target_node_id))
  const outgoingIds = new Set(resultEdgesOnly.map(e => e.source_node_id))
  const rootNodes = nodes.filter(n => !incomingIds.has(n.id))
  const leafNodes = nodes.filter(n => !outgoingIds.has(n.id))

  const avgCenterY = (ns: PipelineNodeOut[]) => {
    if (!ns.length) return svgHeight / 2 - SENTINEL_H / 2
    return ns.reduce((acc, n) => acc + (positions[n.id]?.y ?? 0) + NODE_H / 2, 0) / ns.length - SENTINEL_H / 2
  }

  const startX = 20
  const startY = avgCenterY(rootNodes)
  const endX = 20 + X_OFFSET + layers.length * (NODE_W + GAP_X)
  const endY = avgCenterY(leafNodes)

  const svgWidth = endX + SENTINEL_W + 20

  // Collect unique edge colors so we can define one arrowhead marker per color
  const TOOL_EDGE_COLOR = '#f472b6'
  const edgeColors = new Set<string>([SENTINEL_COLOR, TOOL_EDGE_COLOR])
  edges.forEach(edge => {
    const step = stepMap[edge.target_node_id]
    edgeColors.add(step ? STATUS_COLORS[step.status] ?? '#475569' : '#334155')
  })

  return (
    <svg
      width="100%"
      height="100%"
      viewBox={`0 0 ${svgWidth} ${svgHeight}`}
      style={{ background: '#0a0e14' }}
    >
      <defs>
        <pattern id="dots" x="0" y="0" width="20" height="20" patternUnits="userSpaceOnUse">
          <circle cx="1" cy="1" r="1" fill="#1e293b" />
        </pattern>
        {/* One arrowhead marker per unique edge color */}
        {[...edgeColors].map(c => (
          <marker
            key={c}
            id={`arrow-${c.replace('#', '')}`}
            markerWidth="8"
            markerHeight="8"
            refX="8"
            refY="4"
            orient="auto"
          >
            <path d="M0,0 L8,4 L0,8 Z" fill={c} opacity={0.85} />
          </marker>
        ))}
      </defs>
      <rect width={svgWidth} height={svgHeight} fill="url(#dots)" />

      {/* Sentinel edges: START → roots and leaves → END (dashed, elbow routing) */}
      {rootNodes.map(n => {
        const tgt = positions[n.id]
        if (!tgt) return null
        const x1 = startX + SENTINEL_W
        const y1 = startY + SENTINEL_H / 2
        const x2 = tgt.x - 1
        const y2 = tgt.y + NODE_H / 2
        const midX = x1 + (x2 - x1) * 0.4
        // Elbow: go right to midX, then straight to target Y, then right to node
        const d = y1 === y2
          ? `M${x1},${y1} H${x2}`
          : `M${x1},${y1} H${midX} V${y2} H${x2}`
        return (
          <path
            key={`start-${n.id}`}
            d={d}
            fill="none"
            stroke={SENTINEL_COLOR}
            strokeWidth={1.5}
            strokeDasharray="4 3"
            opacity={0.6}
            markerEnd={`url(#arrow-${SENTINEL_COLOR.replace('#', '')})`}
          />
        )
      })}
      {leafNodes.map(n => {
        const src = positions[n.id]
        if (!src) return null
        const x1 = src.x + NODE_W
        const y1 = src.y + NODE_H / 2
        const x2 = endX - 1
        const y2 = endY + SENTINEL_H / 2
        const midX = x1 + (x2 - x1) * 0.6
        // Elbow: go right to midX, then straight to END Y, then right to END
        const d = y1 === y2
          ? `M${x1},${y1} H${x2}`
          : `M${x1},${y1} H${midX} V${y2} H${x2}`
        return (
          <path
            key={`end-${n.id}`}
            d={d}
            fill="none"
            stroke={SENTINEL_COLOR}
            strokeWidth={1.5}
            strokeDasharray="4 3"
            opacity={0.6}
            markerEnd={`url(#arrow-${SENTINEL_COLOR.replace('#', '')})`}
          />
        )
      })}

      {/* Edges */}
      {edges.map(edge => {
        const isTool = (edge as any).edge_type === 'tool'
        const src = positions[edge.source_node_id]
        const tgt = positions[edge.target_node_id]
        if (!src || !tgt) return null
        const x1 = src.x + NODE_W
        const y1 = src.y + NODE_H / 2
        // End 1px before the node border so the arrowhead tip lands exactly on it
        const x2 = tgt.x - 1
        const y2 = tgt.y + NODE_H / 2
        const step = stepMap[edge.target_node_id]
        const color = isTool ? TOOL_EDGE_COLOR : (step ? STATUS_COLORS[step.status] ?? '#475569' : '#334155')
        const markerId = `arrow-${color.replace('#', '')}`
        const midX = (x1 + x2) / 2
        const midY = (y1 + y2) / 2
        return (
          <g key={edge.id}>
            <path
              d={`M${x1},${y1} C${midX},${y1} ${midX},${y2} ${x2},${y2}`}
              fill="none"
              stroke={color}
              strokeWidth={isTool ? 1.5 : 2}
              strokeDasharray={isTool ? '6 3' : undefined}
              opacity={0.8}
              markerEnd={`url(#${markerId})`}
            />
            {isTool && (
              <text x={midX} y={midY - 6} textAnchor="middle" fill={TOOL_EDGE_COLOR} fontSize={8} fontWeight={600}>
                TOOL
              </text>
            )}
          </g>
        )
      })}

      {/* Nodes */}
      {nodes.map(node => {
        const pos = positions[node.id]
        if (!pos) return null
        const step = stepMap[node.id]
        const color = CATEGORY_COLORS[node.category] ?? '#60a5fa'
        const borderColor = step ? STATUS_COLORS[step.status] ?? color : color

        return (
          <g key={node.id}>
            <rect
              x={pos.x}
              y={pos.y}
              width={NODE_W}
              height={NODE_H}
              rx={8}
              fill="#1e293b"
              stroke={borderColor}
              strokeWidth={2}
            />
            <text x={pos.x + NODE_W / 2} y={pos.y + 18} textAnchor="middle" fill={color} fontSize={9} fontWeight={600}>
              {node.category.toUpperCase()}
            </text>
            <text x={pos.x + NODE_W / 2} y={pos.y + 34} textAnchor="middle" fill="#e2e8f0" fontSize={12} fontWeight={700}>
              {node.label}
            </text>
            {step && (
              <text x={pos.x + NODE_W / 2} y={pos.y + 50} textAnchor="middle" fill={STATUS_COLORS[step.status] ?? '#94a3b8'} fontSize={9}>
                {step.status}{step.item_count > 0 ? ` · ${step.item_count}` : ''}
              </text>
            )}
          </g>
        )
      })}
      {/* START sentinel */}
      <g>
        <rect x={startX} y={startY} width={SENTINEL_W} height={SENTINEL_H} rx={SENTINEL_H / 2}
          fill="#1e293b" stroke={SENTINEL_COLOR} strokeWidth={1.5} strokeDasharray="3 2" opacity={0.8} />
        <text x={startX + SENTINEL_W / 2} y={startY + SENTINEL_H / 2 + 4}
          textAnchor="middle" fill={SENTINEL_COLOR} fontSize={9} fontWeight={700} letterSpacing="0.08em">
          START
        </text>
      </g>

      {/* END sentinel */}
      <g>
        <rect x={endX} y={endY} width={SENTINEL_W} height={SENTINEL_H} rx={SENTINEL_H / 2}
          fill="#1e293b" stroke={SENTINEL_COLOR} strokeWidth={1.5} strokeDasharray="3 2" opacity={0.8} />
        <text x={endX + SENTINEL_W / 2} y={endY + SENTINEL_H / 2 + 4}
          textAnchor="middle" fill={SENTINEL_COLOR} fontSize={9} fontWeight={700} letterSpacing="0.08em">
          END
        </text>
      </g>
    </svg>
  )
}
