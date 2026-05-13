import { useState } from 'react'
import { PipelineNodeOut, PipelineStepRun, NodeType } from '../../api/pipelines'

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
  stepRuns?: PipelineStepRun[]
  nodeTypes?: NodeType[]
  selectedNodeId?: string | null
  invalidNodeIds?: Set<string>
  lockedNodeIds?: Set<string>
  toolNodeIds?: Set<string>
  hiddenCategories?: Set<string>
  onSelect?: (nodeId: string) => void
  onRemove?: (nodeId: string) => void
  onMoveUp?: (nodeId: string) => void
  onMoveDown?: (nodeId: string) => void
  onAdd?: (nodeType: string) => void
  readOnly?: boolean
}

export function StepList({
  nodes,
  stepRuns = [],
  nodeTypes = [],
  selectedNodeId,
  invalidNodeIds = new Set(),
  lockedNodeIds = new Set(),
  toolNodeIds = new Set(),
  hiddenCategories = new Set(),
  onSelect,
  onRemove,
  onMoveUp,
  onMoveDown,
  onAdd,
  readOnly = false,
}: Props) {
  const [insertingAfter, setInsertingAfter] = useState<string | null>(null)

  const stepMap = Object.fromEntries(stepRuns.map(s => [s.node_id, s]))

  const CATEGORY_ORDER = ['source', 'enrich', 'score', 'filter', 'datastore']
  const byCategory: Record<string, NodeType[]> = {}
  for (const nt of nodeTypes) {
    byCategory[nt.category] = byCategory[nt.category] ?? []
    byCategory[nt.category].push(nt)
  }
  const orderedCategories = [
    ...CATEGORY_ORDER.filter(c => byCategory[c]),
    ...Object.keys(byCategory).filter(c => !CATEGORY_ORDER.includes(c)),
  ]

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4, padding: 10, flex: 1, overflowY: 'auto' }}>
      {nodes.map((node, idx) => {
        const step = stepMap[node.id]
        const color = CATEGORY_COLORS[node.category] ?? '#60a5fa'
        const isSelected = node.id === selectedNodeId
        const isInvalid = invalidNodeIds.has(node.id)
        const isTool = toolNodeIds.has(node.id)
        const displayNum = idx + 1
        const isInsertingAfterThis = insertingAfter === node.id
        const canInsert = !readOnly && !isTool && !!onAdd

        return (
          <div key={node.id} style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            {/* Main node row */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <div
                style={{
                  width: 22,
                  height: 22,
                  borderRadius: '50%',
                  background: isTool ? '#f472b6' : color,
                  color: '#000',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: isTool ? 12 : 10,
                  fontWeight: 700,
                  flexShrink: 0,
                }}
                title={isTool ? 'Tool (datastore)' : undefined}
              >
                {isTool ? '⚙' : displayNum}
              </div>
              <div
                onClick={() => onSelect?.(node.id)}
                data-testid={`step-card-${node.node_type}`}
                style={{
                  flex: 1,
                  background: isSelected ? '#1e3a5f' : '#1e293b',
                  border: `1px solid ${isInvalid ? '#ef4444' : isSelected ? color : '#334155'}`,
                  borderLeft: `3px solid ${isInvalid ? '#ef4444' : isSelected ? color : '#334155'}`,
                  borderRadius: 6,
                  padding: '6px 8px',
                  cursor: 'pointer',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontSize: 11, color: '#e2e8f0', fontWeight: 600, display: 'flex', alignItems: 'center', gap: 5 }}>
                    <span style={{ fontSize: 7, color: isInvalid ? '#ef4444' : '#4ade80' }}>●</span>
                    {node.label}{' '}
                    <span style={{ color, fontSize: 9 }}>{node.category.toUpperCase()}</span>
                  </span>
                  {step && (
                    <span style={{ fontSize: 9, color: STATUS_COLORS[step.status] ?? '#94a3b8' }}>
                      {step.status}{step.item_count > 0 ? ` · ${step.item_count}` : ''}
                    </span>
                  )}
                </div>
                <div style={{ fontSize: 9, color: '#94a3b8', marginTop: 2 }}>
                  {node.node_type}
                </div>
              </div>
              {!readOnly && !lockedNodeIds.has(node.id) && !isTool && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                  <button onClick={() => onMoveUp?.(node.id)} disabled={idx === 0} title="Move up" style={{ background: 'transparent', border: '1px solid #334155', borderRadius: 3, color: idx === 0 ? '#1e293b' : '#94a3b8', cursor: idx === 0 ? 'default' : 'pointer', padding: '1px 5px', fontSize: 9, lineHeight: 1 }}>▲</button>
                  <button onClick={() => onMoveDown?.(node.id)} disabled={idx === nodes.length - 1} title="Move down" style={{ background: 'transparent', border: '1px solid #334155', borderRadius: 3, color: idx === nodes.length - 1 ? '#1e293b' : '#94a3b8', cursor: idx === nodes.length - 1 ? 'default' : 'pointer', padding: '1px 5px', fontSize: 9, lineHeight: 1 }}>▼</button>
                  <button onClick={() => onRemove?.(node.id)} title="Remove step" style={{ background: 'transparent', border: '1px solid #334155', borderRadius: 3, color: '#94a3b8', cursor: 'pointer', padding: '1px 5px', fontSize: 11, lineHeight: 1 }}>×</button>
                </div>
              )}
              {lockedNodeIds.has(node.id) && (
                <span
                  title="This node is required and cannot be moved or removed"
                  style={{ fontSize: 8, color: '#60a5fa', padding: '0 4px', fontWeight: 700, letterSpacing: 0.5 }}
                >
                  FIXED
                </span>
              )}
              {isTool && !lockedNodeIds.has(node.id) && (
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2 }}>
                  <span
                    title="Connected as a tool to Intelligent Search"
                    style={{ fontSize: 8, color: '#f472b6', padding: '0 4px', fontWeight: 700, letterSpacing: 0.5 }}
                  >
                    TOOL
                  </span>
                  {!readOnly && (
                    <button onClick={() => onRemove?.(node.id)} title="Remove step" style={{ background: 'transparent', border: '1px solid #334155', borderRadius: 3, color: '#94a3b8', cursor: 'pointer', padding: '1px 5px', fontSize: 11, lineHeight: 1 }}>×</button>
                  )}
                </div>
              )}
            </div>

            {/* Per-node insert affordance: + button or inline select */}
            {canInsert && (
              <div style={{ paddingLeft: 28 }}>
                {isInsertingAfterThis ? (
                  <select
                    autoFocus
                    data-testid={`insert-after-${node.id}`}
                    onChange={e => {
                      if (e.target.value) {
                        onAdd?.(e.target.value)
                        setInsertingAfter(null)
                        e.target.value = ''
                      }
                    }}
                    onBlur={() => setInsertingAfter(null)}
                    style={{
                      width: '100%',
                      padding: '3px 6px',
                      background: '#0f172a',
                      border: '1px dashed #60a5fa',
                      borderRadius: 4,
                      color: '#94a3b8',
                      cursor: 'pointer',
                      fontSize: 10,
                    }}
                    defaultValue=""
                  >
                    <option value="" disabled>Pick node type to insert…</option>
                    {orderedCategories
                      .filter(c => !hiddenCategories.has(c))
                      .map(cat => (
                        <optgroup key={cat} label={cat.toUpperCase()}>
                          {byCategory[cat].map(nt => (
                            <option key={nt.node_type} value={nt.node_type}>
                              {nt.display_name}
                            </option>
                          ))}
                        </optgroup>
                      ))
                    }
                  </select>
                ) : (
                  <button
                    data-testid={`add-after-${node.id}`}
                    onClick={() => setInsertingAfter(node.id)}
                    title="Insert a step after this node"
                    style={{
                      background: 'transparent',
                      border: '1px dashed #334155',
                      borderRadius: 4,
                      color: '#475569',
                      cursor: 'pointer',
                      fontSize: 9,
                      padding: '1px 8px',
                      width: '100%',
                      textAlign: 'center',
                      lineHeight: '16px',
                    }}
                    onMouseEnter={e => { e.currentTarget.style.borderColor = '#60a5fa'; e.currentTarget.style.color = '#60a5fa' }}
                    onMouseLeave={e => { e.currentTarget.style.borderColor = '#334155'; e.currentTarget.style.color = '#475569' }}
                  >
                    +
                  </button>
                )}
              </div>
            )}
          </div>
        )
      })}

      {!readOnly && (
        <div style={{ marginTop: 8 }}>
          <select
            onChange={e => { if (e.target.value) { onAdd?.(e.target.value); e.target.value = '' } }}
            style={{
              width: '100%',
              padding: '5px 8px',
              background: 'transparent',
              border: '1px dashed #334155',
              borderRadius: 4,
              color: '#94a3b8',
              cursor: 'pointer',
              fontSize: 11,
            }}
            defaultValue=""
          >
            <option value="" disabled>+ Add Step</option>
            {orderedCategories
              .filter(c => !hiddenCategories.has(c))
              .map(cat => (
                <optgroup key={cat} label={cat.toUpperCase()}>
                  {byCategory[cat].map(nt => (
                    <option key={nt.node_type} value={nt.node_type}>
                      {nt.display_name}
                    </option>
                  ))}
                </optgroup>
              ))
            }
          </select>
        </div>
      )}
    </div>
  )
}
