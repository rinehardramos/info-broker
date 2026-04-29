import { useState, useRef, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  listPipelines, getPipeline, listNodeTypes, createPipeline, updatePipeline,
  deletePipeline, startPipelineRun, cancelPipelineRun, listPipelineRuns, getPipelineRun,
  PipelineNodeOut, PipelineEdgeOut,
} from '../../api/pipelines'
import { useSessionStore } from '../../stores/sessionStore'
import { ResizableSplit } from './ResizableSplit'
import { StepList } from './StepList'
import { DagPreview } from './DagPreview'
import { NodeConfigForm } from './NodeConfigForm'

export function PipelineBuilder({ initialPipelineId }: { initialPipelineId?: string } = {}) {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const agentInput = useSessionStore(s => s.agentInput)

  const [selectedPipelineId, setSelectedPipelineId] = useState<string | null>(initialPipelineId ?? null)
  const [localNodes, setLocalNodes] = useState<PipelineNodeOut[]>([])
  const [localEdges, setLocalEdges] = useState<PipelineEdgeOut[]>([])
  const [localName, setLocalName] = useState('')
  const [localDesc, setLocalDesc] = useState('')
  const [editingNodeId, setEditingNodeId] = useState<string | null>(null)
  const [activeRunId, setActiveRunId] = useState<string | null>(null)
  const [dirty, setDirty] = useState(false)
  const [creatingNew, setCreatingNew] = useState(false)
  const [newName, setNewName] = useState('')
  const [newDesc, setNewDesc] = useState('')
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [addStepError, setAddStepError] = useState<string | null>(null)

  const { data: pipelines = [] } = useQuery({ queryKey: ['pipelines'], queryFn: listPipelines })
  const { data: nodeTypes = [] } = useQuery({ queryKey: ['nodeTypes'], queryFn: listNodeTypes })
  const { data: pipelineDetail } = useQuery({
    queryKey: ['pipeline', selectedPipelineId],
    queryFn: () => getPipeline(selectedPipelineId!),
    enabled: !!selectedPipelineId,
  })
  const { data: runs = [] } = useQuery({
    queryKey: ['pipelineRuns', selectedPipelineId],
    queryFn: () => listPipelineRuns(selectedPipelineId!),
    enabled: !!selectedPipelineId,
    refetchInterval: 5000,
  })
  const { data: activeRun } = useQuery({
    queryKey: ['pipelineRun', activeRunId],
    queryFn: () => getPipelineRun(activeRunId!),
    enabled: !!activeRunId,
    refetchInterval: activeRunId ? 3000 : false,
  })

  const createMutation = useMutation({
    mutationFn: createPipeline,
    onSuccess: p => {
      qc.invalidateQueries({ queryKey: ['pipelines'] })
      setSelectedPipelineId(p.id)
      setLocalNodes([])
      setLocalEdges([])
      setCreatingNew(false)
      setNewName('')
      setNewDesc('')
      setDirty(false)
      navigate(`/pipelines/${p.id}`, { replace: true })
    },
  })
  const updateMutation = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Parameters<typeof updatePipeline>[1] }) =>
      updatePipeline(id, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['pipelines'] })
      qc.invalidateQueries({ queryKey: ['pipeline', selectedPipelineId] })
      setDirty(false)
    },
  })
  const deleteMutation = useMutation({
    mutationFn: deletePipeline,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['pipelines'] })
      setSelectedPipelineId(null)
      setLocalNodes([])
      setLocalEdges([])
      setLocalName('')
      setConfirmDelete(false)
    },
  })
  const [runError, setRunError] = useState<string | null>(null)
  const runMutation = useMutation({
    mutationFn: ({ id, variables }: { id: string; variables?: Record<string, string> }) =>
      startPipelineRun(id, variables),
    onSuccess: run => {
      setRunError(null)
      setActiveRunId(run.id)
      qc.invalidateQueries({ queryKey: ['pipelineRuns', selectedPipelineId] })
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { detail?: string } }; message?: string })
        ?.response?.data?.detail ?? (err as { message?: string })?.message ?? 'Failed to start run'
      setRunError(msg)
    },
  })
  const cancelMutation = useMutation({
    mutationFn: cancelPipelineRun,
    onSuccess: () => {
      setActiveRunId(null)
      qc.invalidateQueries({ queryKey: ['pipelineRuns', selectedPipelineId] })
      qc.invalidateQueries({ queryKey: ['pipelineRun', activeRunId] })
    },
  })

  // Load pipeline into local state when selected (useEffect avoids race with user interactions)
  const prevPipelineId = useRef<string | null>(null)
  useEffect(() => {
    if (!pipelineDetail) return
    if (pipelineDetail.id === prevPipelineId.current) return
    prevPipelineId.current = pipelineDetail.id
    // Enrich nodes with category from nodeTypes registry
    const enriched = pipelineDetail.nodes.map(n => ({
      ...n,
      category: n.category || nodeTypes.find(t => t.node_type === n.node_type)?.category || 'source',
    }))
    setLocalNodes(enriched)
    setLocalEdges(pipelineDetail.edges)
    setLocalName(pipelineDetail.name)
    setLocalDesc(pipelineDetail.description ?? '')
    setDirty(false)
  }, [pipelineDetail, nodeTypes])

  const handleAddNode = (nodeType: string) => {
    const nt = nodeTypes.find(t => t.node_type === nodeType)
    if (!nt) return
    setAddStepError(null)

    // Read current state directly — event handlers always see the latest snapshot.
    // Avoids calling setLocalEdges as a side-effect inside a setLocalNodes updater,
    // which React may invoke multiple times and which reads stale edge state.
    const cur = localNodes
    const curEdges = localEdges

    const rawSources = cur.filter(n => n.category === 'source' && n.node_type !== 'aggregator')
    const aggregatorNode = cur.find(n => n.node_type === 'aggregator')
    const nonSources = cur.filter(n => n.category !== 'source')

    const mkNode = (): PipelineNodeOut => ({
      id: crypto.randomUUID(), node_type: nt.node_type, label: nt.display_name,
      config: {}, category: nt.category, position_x: 0, position_y: 0,
    })
    const mkEdge = (src: string, tgt: string): PipelineEdgeOut =>
      ({ id: crypto.randomUUID(), source_node_id: src, target_node_id: tgt, edge_type: 'results' })

    if (nt.category === 'source') {
      if (nt.node_type === 'aggregator') {
        // Aggregator is always the last source: fan-in all raw sources → agg → non-source chain
        const agg = mkNode()
        const newNodes = [...rawSources, agg, ...nonSources]
        const newEdges: PipelineEdgeOut[] = [
          ...rawSources.map(s => mkEdge(s.id, agg.id)),
          ...[agg, ...nonSources].slice(1).map((n, i) => mkEdge([agg, ...nonSources][i].id, n.id)),
        ]
        setLocalNodes(newNodes)
        setLocalEdges(newEdges)
        setDirty(true)
        return
      }

      if (rawSources.length >= 1 && !aggregatorNode) {
        setAddStepError('Add an Aggregator step to merge multiple sources.')
        return
      }

      const newNode = mkNode()
      if (aggregatorNode) {
        // Insert before aggregator, wire newNode → aggregator only
        setLocalNodes([...rawSources, newNode, aggregatorNode, ...nonSources])
        setLocalEdges([...curEdges, mkEdge(newNode.id, aggregatorNode.id)])
      } else {
        // First source: prepend, chain into existing non-source list
        const newNodes = [newNode, ...nonSources]
        const newEdges = nonSources.length > 0 ? [mkEdge(newNode.id, nonSources[0].id)] : []
        setLocalNodes(newNodes)
        setLocalEdges(newEdges)
      }
      setDirty(true)
      return
    }

    // Non-source: always append sequentially to the end of the list
    const newNode = mkNode()
    const newEdge = cur.length > 0 ? [mkEdge(cur[cur.length - 1].id, newNode.id)] : []
    setLocalNodes([...cur, newNode])
    setLocalEdges([...curEdges, ...newEdge])
    setDirty(true)
  }

  const handleRemoveNode = (nodeId: string) => {
    setLocalNodes(prev => prev.filter(n => n.id !== nodeId))
    setLocalEdges(prev => prev.filter(e => e.source_node_id !== nodeId && e.target_node_id !== nodeId))
    if (editingNodeId === nodeId) setEditingNodeId(null)
    setDirty(true)
  }

  const handleConfigChange = (nodeId: string, config: Record<string, unknown>) => {
    setLocalNodes(prev => prev.map(n => n.id === nodeId ? { ...n, config } : n))
    setDirty(true)
  }

  const handleMoveNode = (nodeId: string, direction: 'up' | 'down') => {
    const idx = localNodes.findIndex(n => n.id === nodeId)
    if (idx === -1) return
    const swapIdx = direction === 'up' ? idx - 1 : idx + 1
    if (swapIdx < 0 || swapIdx >= localNodes.length) return
    const next = [...localNodes]
    ;[next[idx], next[swapIdx]] = [next[swapIdx], next[idx]]
    setLocalNodes(next)
    setDirty(true)
  }

  const handleEdgeChange = (sourceId: string, targetId: string, connected: boolean) => {
    if (connected) {
      const newEdge: PipelineEdgeOut = {
        id: crypto.randomUUID(),
        pipeline_id: selectedPipelineId ?? '',
        source_node_id: sourceId,
        target_node_id: targetId,
        edge_type: 'default',
      }
      setLocalEdges(prev => [...prev, newEdge])
    } else {
      setLocalEdges(prev => prev.filter(e => !(e.source_node_id === sourceId && e.target_node_id === targetId)))
    }
    setDirty(true)
  }

  const handleSave = () => {
    if (!selectedPipelineId) return
    updateMutation.mutate({
      id: selectedPipelineId,
      body: {
        name: localName,
        description: localDesc || null,
        nodes: localNodes.map(n => ({
          id: n.id,
          node_type: n.node_type,
          label: n.label,
          config: n.config,
          position_x: n.position_x,
          position_y: n.position_y,
        })),
        edges: localEdges.map(e => ({
          source_node_id: e.source_node_id,
          target_node_id: e.target_node_id,
          edge_type: e.edge_type,
        })),
      },
    })
  }

  const handleCreateSubmit = () => {
    const name = newName.trim()
    if (!name) return
    createMutation.mutate({
      name,
      description: newDesc.trim() || null,
      nodes: [],
      edges: [],
    })
  }

  const handleRun = () => {
    if (!selectedPipelineId) return
    runMutation.mutate({ id: selectedPipelineId, variables: agentInput ? { agent_input: agentInput } : undefined })
  }

  const handleDelete = () => {
    if (!selectedPipelineId) return
    deleteMutation.mutate(selectedPipelineId)
  }

  const isRunning = activeRun?.status === 'running'
  const stepRuns = activeRun?.steps ?? []
  const sourceCount = localNodes.filter(n => n.category === 'source' && n.node_type !== 'aggregator').length
  const hasAggregator = localNodes.some(n => n.node_type === 'aggregator')
  const hasSource = sourceCount > 0
  const needsAggregator = sourceCount > 1 && !hasAggregator
  const noSourceHint = selectedPipelineId && localNodes.length > 0 && !hasSource
  const editingNode = editingNodeId ? localNodes.find(n => n.id === editingNodeId) ?? null : null
  const editingNodeType = editingNode ? nodeTypes.find(t => t.node_type === editingNode.node_type) : null

  // Required-field validation: a node is invalid when it has a required field
  // with no value and no schema default (enum fields always have an implicit default).
  const invalidNodeIds = new Set<string>(
    localNodes
      .filter(node => {
        const nt = nodeTypes.find(t => t.node_type === node.node_type)
        if (!nt) return false
        const schema = nt.config_schema as { properties?: Record<string, { default?: unknown; enum?: string[] }>; required?: string[] }
        const requiredFields = schema.required ?? []
        const props = schema.properties ?? {}
        return requiredFields.some(field => {
          const val = node.config[field]
          if (val !== undefined && val !== null && val !== '') return false
          if (props[field]?.default !== undefined) return false
          if (props[field]?.enum?.length) return false
          return true
        })
      })
      .map(n => n.id),
  )
  const invalidCount = invalidNodeIds.size
  const canSave = dirty && invalidCount === 0
  const canRun = !!selectedPipelineId && !isRunning && hasSource && !needsAggregator && invalidCount === 0

  // Compute topological order so StepList numbers match DAG flow
  const topoOrderMap = (() => {
    const validIds = new Set(localNodes.map(n => n.id))
    const deps: Record<string, Set<string>> = {}
    for (const n of localNodes) deps[n.id] = new Set()
    for (const e of localEdges) {
      if (deps[e.target_node_id] && validIds.has(e.source_node_id)) {
        deps[e.target_node_id].add(e.source_node_id)
      }
    }
    const order: Record<string, number> = {}
    const resolved = new Set<string>()
    let i = 0
    while (resolved.size < localNodes.length) {
      const batch = localNodes.filter(n => !resolved.has(n.id) && [...deps[n.id]].every(d => resolved.has(d)))
      if (!batch.length) break
      batch.forEach(n => { order[n.id] = i++; resolved.add(n.id) })
    }
    // Assign remaining (cycles/disconnected) in array order
    localNodes.filter(n => !resolved.has(n.id)).forEach(n => { order[n.id] = i++ })
    return order
  })()

  return (
    <div style={{ display: 'flex', height: '100%', background: '#0d1117', color: '#e2e8f0', overflow: 'hidden' }}>
      {/* Saved pipelines sidebar */}
      <div style={{ width: 180, borderRight: '1px solid #1e293b', display: 'flex', flexDirection: 'column' }}>
        <div style={{ padding: '8px', borderBottom: '1px solid #1e293b', fontSize: 11, color: '#94a3b8' }}>PIPELINES</div>
        <div style={{ flex: 1, overflowY: 'auto' }}>
          {pipelines.map(p => (
            <div
              key={p.id}
              onClick={() => { setSelectedPipelineId(p.id); setActiveRunId(null); setCreatingNew(false); navigate(`/pipelines/${p.id}`, { replace: true }) }}
              style={{
                padding: '8px 10px',
                cursor: 'pointer',
                background: p.id === selectedPipelineId && !creatingNew ? '#1e293b' : 'transparent',
                borderLeft: p.id === selectedPipelineId && !creatingNew ? '2px solid #60a5fa' : '2px solid transparent',
                fontSize: 11,
              }}
            >
              {p.name}
            </div>
          ))}
        </div>

        {/* Inline new pipeline form */}
        {creatingNew ? (
          <div style={{ borderTop: '1px solid #1e293b', padding: 8, display: 'flex', flexDirection: 'column', gap: 6 }}>
            <input
              autoFocus
              placeholder="Pipeline name *"
              value={newName}
              onChange={e => setNewName(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') handleCreateSubmit(); if (e.key === 'Escape') setCreatingNew(false) }}
              style={{ padding: '4px 6px', fontSize: 11, background: '#1e293b', border: '1px solid #334155', borderRadius: 4, color: '#e2e8f0', outline: 'none', width: '100%', boxSizing: 'border-box' }}
            />
            <input
              placeholder="Description (optional)"
              value={newDesc}
              onChange={e => setNewDesc(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') handleCreateSubmit(); if (e.key === 'Escape') setCreatingNew(false) }}
              style={{ padding: '4px 6px', fontSize: 11, background: '#1e293b', border: '1px solid #334155', borderRadius: 4, color: '#e2e8f0', outline: 'none', width: '100%', boxSizing: 'border-box' }}
            />
            <div style={{ display: 'flex', gap: 4 }}>
              <button
                onClick={handleCreateSubmit}
                disabled={!newName.trim() || createMutation.isPending}
                style={{ flex: 1, padding: '4px 0', fontSize: 10, fontWeight: 700, background: newName.trim() ? '#60a5fa' : '#1e293b', color: newName.trim() ? '#0d1117' : '#475569', border: 'none', borderRadius: 4, cursor: newName.trim() ? 'pointer' : 'default' }}
              >
                {createMutation.isPending ? '…' : 'Create'}
              </button>
              <button
                onClick={() => { setCreatingNew(false); setNewName(''); setNewDesc('') }}
                style={{ padding: '4px 8px', fontSize: 10, background: 'transparent', color: '#94a3b8', border: '1px solid #334155', borderRadius: 4, cursor: 'pointer' }}
              >
                Cancel
              </button>
            </div>
          </div>
        ) : (
          <button
            onClick={() => { setCreatingNew(true); setNewName(''); setNewDesc('') }}
            style={{ padding: '8px', fontSize: 11, background: 'transparent', border: 'none', borderTop: '1px solid #1e293b', color: '#60a5fa', cursor: 'pointer' }}
          >
            + New Pipeline
          </button>
        )}
      </div>

      {/* Main area */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {/* Header — pipeline name only */}
        <div style={{ display: 'flex', alignItems: 'center', padding: '8px 12px', borderBottom: '1px solid #1e293b' }}>
          <input
            value={localName}
            onChange={e => { setLocalName(e.target.value); setDirty(true) }}
            style={{ flex: 1, background: 'transparent', border: 'none', color: '#e2e8f0', fontSize: 13, fontWeight: 600, outline: 'none' }}
          />
        </div>

        {/* Resizable panels */}
        <div style={{ flex: 1, position: 'relative', overflow: 'hidden' }}>
          <ResizableSplit
            left={
              <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
                <StepList
                  nodes={localNodes}
                  stepRuns={stepRuns}
                  nodeTypes={nodeTypes}
                  selectedNodeId={editingNodeId}
                  invalidNodeIds={invalidNodeIds}
                  topoOrderMap={topoOrderMap}
                  onSelect={setEditingNodeId}
                  onRemove={handleRemoveNode}
                  onMoveUp={id => handleMoveNode(id, 'up')}
                  onMoveDown={id => handleMoveNode(id, 'down')}
                  onAdd={handleAddNode}
                  readOnly={isRunning}
                />
                {/* Action buttons pinned below the step list */}
                {noSourceHint && (
                  <div style={{ padding: '4px 10px', fontSize: 10, color: '#facc15', background: '#facc1511', borderTop: '1px solid #facc1533' }}>
                    Add a source step before running
                  </div>
                )}
                {needsAggregator && (
                  <div style={{ padding: '4px 10px', fontSize: 10, color: '#f87171', background: '#ef444411', borderTop: '1px solid #ef444433' }}>
                    Multiple sources require an Aggregator step
                  </div>
                )}
                {addStepError && (
                  <div style={{ padding: '4px 10px', fontSize: 10, color: '#f87171', background: '#ef444411', borderTop: '1px solid #ef444433' }}>
                    {addStepError}
                  </div>
                )}
                {invalidCount > 0 && dirty && (
                  <div style={{ padding: '4px 10px', fontSize: 10, color: '#f87171', background: '#ef444411', borderTop: '1px solid #ef444433' }}>
                    {invalidCount} step{invalidCount > 1 ? 's' : ''} have required fields missing
                  </div>
                )}
                {runError && (
                  <div style={{ padding: '4px 10px', fontSize: 10, color: '#f87171', background: '#ef444411', borderTop: '1px solid #ef444433' }}>
                    {runError}
                  </div>
                )}
                {confirmDelete ? (
                  <div style={{ flexShrink: 0, borderTop: '1px solid #ef4444' }}>
                    <div style={{ padding: '5px 10px', fontSize: 10, color: '#fca5a5', background: '#7f1d1d22' }}>
                      Permanently delete "{localName}"?
                    </div>
                    <div style={{ display: 'flex', gap: 6, padding: '6px 10px' }}>
                      <button
                        onClick={() => setConfirmDelete(false)}
                        style={{ flex: 1, padding: '5px 0', fontSize: 11, background: 'transparent', border: '1px solid #334155', borderRadius: 4, color: '#94a3b8', cursor: 'pointer' }}
                      >
                        Cancel
                      </button>
                      <button
                        onClick={handleDelete}
                        disabled={deleteMutation.isPending}
                        style={{ flex: 1, padding: '5px 0', fontSize: 11, background: '#7f1d1d', border: '1px solid #ef4444', borderRadius: 4, color: '#fca5a5', fontWeight: 700, cursor: 'pointer', opacity: deleteMutation.isPending ? 0.6 : 1 }}
                      >
                        {deleteMutation.isPending ? 'Deleting…' : 'Delete'}
                      </button>
                    </div>
                  </div>
                ) : (
                  <div style={{ display: 'flex', gap: 6, padding: '8px 10px', borderTop: '1px solid #1e293b', flexShrink: 0 }}>
                    <button
                      onClick={handleSave}
                      disabled={!canSave}
                      style={{ flex: 1, padding: '5px 0', fontSize: 11, background: canSave ? '#1e293b' : 'transparent', border: '1px solid #334155', borderRadius: 4, color: canSave ? '#e2e8f0' : '#475569', cursor: canSave ? 'pointer' : 'default' }}
                    >
                      Save
                    </button>
                    {isRunning ? (
                      <button
                        onClick={() => activeRunId && cancelMutation.mutate(activeRunId)}
                        disabled={cancelMutation.isPending}
                        style={{ flex: 1, padding: '5px 0', fontSize: 11, background: '#ef4444', border: 'none', borderRadius: 4, color: '#fff', fontWeight: 700, cursor: 'pointer', opacity: cancelMutation.isPending ? 0.6 : 1 }}
                      >
                        {cancelMutation.isPending ? 'Stopping...' : 'Stop'}
                      </button>
                    ) : (
                      <button
                        onClick={() => { setRunError(null); handleRun() }}
                        disabled={!canRun}
                        style={{ flex: 1, padding: '5px 0', fontSize: 11, background: '#60a5fa', border: 'none', borderRadius: 4, color: '#0d1117', fontWeight: 700, cursor: canRun ? 'pointer' : 'default', opacity: canRun ? 1 : 0.4 }}
                      >
                        Run
                      </button>
                    )}
                    {selectedPipelineId && (
                      <button
                        onClick={() => setConfirmDelete(true)}
                        style={{ padding: '5px 10px', fontSize: 11, background: 'transparent', border: '1px solid #334155', borderRadius: 4, color: '#f87171', cursor: 'pointer' }}
                      >
                        Delete
                      </button>
                    )}
                  </div>
                )}
              </div>
            }
            right={
              <DagPreview nodes={localNodes} edges={localEdges} stepRuns={stepRuns} />
            }
          />
          {editingNode && editingNodeType && (
            <NodeConfigForm
              node={editingNode}
              schema={editingNodeType.config_schema}
              onChange={handleConfigChange}
              onClose={() => setEditingNodeId(null)}
              onDone={() => { setEditingNodeId(null); if (selectedPipelineId) handleSave() }}
              nodes={localNodes}
              edges={localEdges}
              onEdgeChange={handleEdgeChange}
            />
          )}
        </div>
      </div>
    </div>
  )
}
