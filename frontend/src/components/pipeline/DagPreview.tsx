import { PipelineNodeOut, PipelineEdgeOut, PipelineStepRun } from '../../api/pipelines'

const NODE_W = 160
const NODE_H = 60
const GAP_X = 80
const GAP_Y = 30

const CATEGORY_COLORS: Record<string, string> = {
  source: '#60a5fa',
  enrich: '#a78bfa',
  score: '#4ade80',
  filter: '#fb923c',
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
  const deps: Record<string, Set<string>> = {}
  for (const n of nodes) deps[n.id] = new Set()
  for (const e of edges) {
    if (deps[e.target_node_id]) deps[e.target_node_id].add(e.source_node_id)
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

  // Compute positions
  const positions: Record<string, { x: number; y: number }> = {}
  let maxY = 0
  layers.forEach((layer, layerIdx) => {
    const totalH = layer.length * NODE_H + (layer.length - 1) * GAP_Y
    layer.forEach((node, nodeIdx) => {
      const x = 20 + layerIdx * (NODE_W + GAP_X)
      const y = 20 + nodeIdx * (NODE_H + GAP_Y)
      positions[node.id] = { x, y }
      maxY = Math.max(maxY, y + NODE_H)
    })
  })

  const svgWidth = 20 + layers.length * (NODE_W + GAP_X) + 20
  const svgHeight = maxY + 40

  // Collect unique edge colors so we can define one arrowhead marker per color
  const edgeColors = new Set<string>()
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

      {/* Edges */}
      {edges.map(edge => {
        const src = positions[edge.source_node_id]
        const tgt = positions[edge.target_node_id]
        if (!src || !tgt) return null
        const x1 = src.x + NODE_W
        const y1 = src.y + NODE_H / 2
        // End 1px before the node border so the arrowhead tip lands exactly on it
        const x2 = tgt.x - 1
        const y2 = tgt.y + NODE_H / 2
        const step = stepMap[edge.target_node_id]
        const color = step ? STATUS_COLORS[step.status] ?? '#475569' : '#334155'
        const markerId = `arrow-${color.replace('#', '')}`
        return (
          <path
            key={edge.id}
            d={`M${x1},${y1} C${(x1 + x2) / 2},${y1} ${(x1 + x2) / 2},${y2} ${x2},${y2}`}
            fill="none"
            stroke={color}
            strokeWidth={2}
            opacity={0.8}
            markerEnd={`url(#${markerId})`}
          />
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
    </svg>
  )
}
