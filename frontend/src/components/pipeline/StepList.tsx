import { PipelineNodeOut, PipelineStepRun, NodeType } from '../../api/pipelines'

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
  stepRuns?: PipelineStepRun[]
  nodeTypes?: NodeType[]
  selectedNodeId?: string | null
  invalidNodeIds?: Set<string>
  onSelect?: (nodeId: string) => void
  onRemove?: (nodeId: string) => void
  onAdd?: (nodeType: string) => void
  readOnly?: boolean
}

export function StepList({
  nodes,
  stepRuns = [],
  nodeTypes = [],
  selectedNodeId,
  invalidNodeIds = new Set(),
  onSelect,
  onRemove,
  onAdd,
  readOnly = false,
}: Props) {
  const stepMap = Object.fromEntries(stepRuns.map(s => [s.node_id, s]))

  const CATEGORY_ORDER = ['source', 'enrich', 'score', 'filter']
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

        return (
          <div key={node.id} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <div
              style={{
                width: 22,
                height: 22,
                borderRadius: '50%',
                background: color,
                color: '#000',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: 10,
                fontWeight: 700,
                flexShrink: 0,
              }}
            >
              {idx + 1}
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
            {!readOnly && (
              <button
                onClick={() => onRemove?.(node.id)}
                style={{
                  background: 'transparent',
                  border: '1px solid #334155',
                  borderRadius: 4,
                  color: '#94a3b8',
                  cursor: 'pointer',
                  padding: '2px 5px',
                  fontSize: 11,
                }}
              >
                ×
              </button>
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
            {orderedCategories.map(cat => (
              <optgroup key={cat} label={cat.toUpperCase()}>
                {byCategory[cat].map(nt => (
                  <option key={nt.node_type} value={nt.node_type}>
                    {nt.display_name}
                  </option>
                ))}
              </optgroup>
            ))}
          </select>
        </div>
      )}
    </div>
  )
}
