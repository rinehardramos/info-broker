/**
 * InvestigationDAG — full investigation graph for completed (and in-progress) runs.
 *
 * Renders a hierarchical top-down DAG using absolute positioning + SVG edges.
 * No external DAG/graph library — hand-rolled grid layout via buildDagFromRun.
 *
 * Layout:
 *   Query → Phase(s) → Tactician columns → Finding nodes → Ranked candidates
 *
 * Interactions:
 *   - Pan: drag the canvas
 *   - Zoom: Ctrl+scroll or pinch
 *   - Hover: tooltip via title attribute (native)
 *   - Click tactician: propagates to parent filter (onSelectTactician)
 */

import React, { useRef, useState, useCallback, useEffect } from 'react'
import { useRunStreamStore } from '@/stores/runStreamStore'
import { buildDagFromRun, type DagNode, type DagEdge } from './dag/buildDagFromRun'
import { PhaseNode } from './dag/PhaseNode'
import { TacticianNode } from './dag/TacticianNode'
import { FindingNode } from './dag/FindingNode'
import { CandidateNode } from './dag/CandidateNode'

const CANVAS_PADDING = 40

// ─── SVG Edges ────────────────────────────────────────────────────────────────

const EDGE_LABEL_COLOR: Record<NonNullable<DagEdge['labelKind']>, string> = {
  pass:     '#22c55e',
  fail:     '#ef4444',
  ask_user: '#fbbf24',
}

function EdgeLayer({
  edges,
  nodeById,
}: {
  edges: DagEdge[]
  nodeById: Map<string, DagNode>
}) {
  return (
    <g>
      {edges.map((edge) => {
        const src = nodeById.get(edge.sourceId)
        const tgt = nodeById.get(edge.targetId)
        if (!src || !tgt) return null

        const x1 = src.x + src.width / 2
        const y1 = src.y + src.height
        const x2 = tgt.x + tgt.width / 2
        const y2 = tgt.y

        const cy = (y1 + y2) / 2
        const d = `M ${x1} ${y1} C ${x1} ${cy}, ${x2} ${cy}, ${x2} ${y2}`
        const labelColor = edge.labelKind ? EDGE_LABEL_COLOR[edge.labelKind] : undefined

        return (
          <g key={edge.id}>
            <path
              d={d}
              fill="none"
              stroke={labelColor ?? 'currentColor'}
              strokeWidth={labelColor ? 1.5 : 1}
              strokeOpacity={labelColor ? 0.55 : 0.25}
              className={labelColor ? undefined : 'text-slate-500'}
            />
            {edge.label && (
              <g>
                {/* small dark backdrop so label stays readable over node grid */}
                <rect
                  x={(x1 + x2) / 2 - edge.label.length * 3.2}
                  y={cy - 7}
                  width={edge.label.length * 6.4}
                  height={13}
                  rx={3}
                  fill="rgb(2,6,23)"
                  stroke={labelColor ?? '#475569'}
                  strokeOpacity={0.6}
                />
                <text
                  x={(x1 + x2) / 2}
                  y={cy + 3}
                  textAnchor="middle"
                  fontSize="9"
                  fontWeight="600"
                  fill={labelColor ?? '#94a3b8'}
                  style={{ fontFamily: 'system-ui, sans-serif' }}
                >
                  {edge.label}
                </text>
              </g>
            )}
          </g>
        )
      })}
    </g>
  )
}

// ─── Node renderer ────────────────────────────────────────────────────────────

function NodeRenderer({
  node,
  onClickTactician,
}: {
  node: DagNode
  onClickTactician?: (phaseId: string, slotIdx: number) => void
}) {
  const style: React.CSSProperties = {
    position: 'absolute',
    left: node.x,
    top: node.y,
    width: node.width,
    height: node.height,
  }

  const { data } = node

  if (data.kind === 'query') {
    return (
      <div style={style}>
        <div className="w-full h-full rounded-full border border-slate-600 bg-slate-800/80 flex items-center justify-center px-3">
          <span className="text-[11px] font-bold text-slate-300 truncate">
            {data.label}
          </span>
        </div>
      </div>
    )
  }

  if (data.kind === 'phase') {
    return (
      <div style={style}>
        <PhaseNode data={data} />
      </div>
    )
  }

  if (data.kind === 'tactician') {
    return (
      <div style={style}>
        <TacticianNode
          data={data}
          onClick={
            onClickTactician
              ? () => onClickTactician(data.phaseId, data.slotIdx)
              : undefined
          }
        />
      </div>
    )
  }

  if (data.kind === 'finding') {
    return (
      <div style={style}>
        <FindingNode data={data} />
      </div>
    )
  }

  if (data.kind === 'candidate') {
    return (
      <div style={style}>
        <CandidateNode data={data} />
      </div>
    )
  }

  return null
}

// ─── Pan/zoom hook ────────────────────────────────────────────────────────────

interface Transform {
  x: number
  y: number
  scale: number
}

function usePanZoom(containerRef: React.RefObject<HTMLDivElement | null>) {
  const [transform, setTransform] = useState<Transform>({ x: CANVAS_PADDING, y: CANVAS_PADDING, scale: 1 })
  const dragging = useRef(false)
  const lastPos = useRef({ x: 0, y: 0 })

  const onMouseDown = useCallback((e: React.MouseEvent) => {
    if (e.button !== 0) return
    dragging.current = true
    lastPos.current = { x: e.clientX, y: e.clientY }
    e.preventDefault()
  }, [])

  const onMouseMove = useCallback((e: React.MouseEvent) => {
    if (!dragging.current) return
    const dx = e.clientX - lastPos.current.x
    const dy = e.clientY - lastPos.current.y
    lastPos.current = { x: e.clientX, y: e.clientY }
    setTransform(t => ({ ...t, x: t.x + dx, y: t.y + dy }))
  }, [])

  const onMouseUp = useCallback(() => { dragging.current = false }, [])

  const onWheel = useCallback((e: WheelEvent) => {
    if (!e.ctrlKey && !e.metaKey) return
    e.preventDefault()
    const delta = e.deltaY > 0 ? 0.9 : 1.1
    setTransform(t => {
      const next = Math.max(0.2, Math.min(2.5, t.scale * delta))
      return { ...t, scale: next }
    })
  }, [])

  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    el.addEventListener('wheel', onWheel, { passive: false })
    return () => el.removeEventListener('wheel', onWheel)
  }, [containerRef, onWheel])

  const fitToView = useCallback((totalW: number, totalH: number) => {
    const el = containerRef.current
    if (!el) return
    const { width, height } = el.getBoundingClientRect()
    const scaleX = (width - CANVAS_PADDING * 2) / Math.max(totalW, 1)
    const scaleY = (height - CANVAS_PADDING * 2) / Math.max(totalH, 1)
    const fitScale = Math.min(scaleX, scaleY, 1)
    setTransform({
      x: Math.max(CANVAS_PADDING, (width - totalW * fitScale) / 2),
      y: CANVAS_PADDING,
      scale: fitScale,
    })
  }, [containerRef])

  return { transform, onMouseDown, onMouseMove, onMouseUp, fitToView }
}

// ─── Main component ───────────────────────────────────────────────────────────

interface InvestigationDAGProps {
  runId: string
  onSelectTactician?: (filter: { phaseId: string; slotIdx: number } | null) => void
}

export function InvestigationDAG({ runId, onSelectTactician }: InvestigationDAGProps) {
  const run = useRunStreamStore(s => s.runsById[runId])
  const containerRef = useRef<HTMLDivElement>(null)
  const { transform, onMouseDown, onMouseMove, onMouseUp, fitToView } = usePanZoom(containerRef)
  // Pruned candidates visible by default per design decision; toolbar toggles.
  const [showPruned, setShowPruned] = useState(true)

  const fullGraph = buildDagFromRun(run)
  const { nodes, edges, totalWidth, totalHeight } = showPruned
    ? fullGraph
    : (() => {
        const dropIds = new Set(
          fullGraph.nodes
            .filter((n) => n.data.kind === 'candidate' && n.data.isPruned)
            .map((n) => n.id),
        )
        return {
          ...fullGraph,
          nodes: fullGraph.nodes.filter((n) => !dropIds.has(n.id)),
          edges: fullGraph.edges.filter((e) => !dropIds.has(e.targetId) && !dropIds.has(e.sourceId)),
        }
      })()

  const nodeById = new Map<string, DagNode>(nodes.map(n => [n.id, n]))

  const canvasW = totalWidth + CANVAS_PADDING * 2
  const canvasH = totalHeight + CANVAS_PADDING * 2

  function handleTacticianClick(phaseId: string, slotIdx: number) {
    onSelectTactician?.({ phaseId, slotIdx })
  }

  if (nodes.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-[11px] text-slate-600 italic px-4">
        No investigation data yet — waiting for phases...
      </div>
    )
  }

  return (
    <div
      ref={containerRef}
      className="relative w-full h-full overflow-hidden bg-slate-950 select-none"
      style={{ cursor: 'grab' }}
      onMouseDown={onMouseDown}
      onMouseMove={onMouseMove}
      onMouseUp={onMouseUp}
      onMouseLeave={onMouseUp}
      role="img"
      aria-label="Investigation DAG — pan with drag, zoom with Ctrl+scroll"
    >
      {/* Toolbar */}
      <div className="absolute top-2 right-2 z-10 flex items-center gap-1">
        <button
          type="button"
          className={[
            'text-[10px] border rounded px-2 py-0.5 bg-slate-900/80 transition-colors',
            showPruned
              ? 'text-slate-300 border-slate-600'
              : 'text-slate-500 border-slate-700 hover:text-slate-300',
          ].join(' ')}
          onClick={(e) => { e.stopPropagation(); setShowPruned((v) => !v) }}
          onMouseDown={(e) => e.stopPropagation()}
          title={showPruned ? 'Hide pruned candidates' : 'Show pruned candidates'}
        >
          {showPruned ? '✓ pruned' : 'pruned hidden'}
        </button>
        <button
          type="button"
          className="text-[10px] text-slate-500 hover:text-slate-300 border border-slate-700 rounded px-2 py-0.5 bg-slate-900/80 transition-colors"
          onClick={(e) => { e.stopPropagation(); fitToView(totalWidth, totalHeight) }}
          title="Fit graph to view"
          onMouseDown={(e) => e.stopPropagation()}
        >
          fit
        </button>
      </div>

      {/* Transformed canvas */}
      <div
        style={{
          position: 'absolute',
          transform: `translate(${transform.x}px, ${transform.y}px) scale(${transform.scale})`,
          transformOrigin: '0 0',
          width: canvasW,
          height: canvasH,
        }}
      >
        {/* SVG edge layer */}
        <svg
          style={{
            position: 'absolute',
            inset: 0,
            width: canvasW,
            height: canvasH,
            overflow: 'visible',
            pointerEvents: 'none',
          }}
          aria-hidden="true"
        >
          <EdgeLayer edges={edges} nodeById={nodeById} />
        </svg>

        {/* Node layer */}
        {nodes.map(node => (
          <NodeRenderer
            key={node.id}
            node={node}
            onClickTactician={handleTacticianClick}
          />
        ))}
      </div>
    </div>
  )
}
