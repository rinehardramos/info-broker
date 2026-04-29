import { useState, useRef, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  listPipelines, getPipeline, listNodeTypes, createPipeline, updatePipeline,
  deletePipeline, startPipelineRun, cancelPipelineRun, listPipelineRuns, getPipelineRun,
  PipelineNodeOut, PipelineEdgeOut,
} from '../../api/pipelines'
import { ResizableSplit } from './ResizableSplit'
import { StepList } from './StepList'
import { DagPreview } from './DagPreview'
import { NodeConfigForm } from './NodeConfigForm'

export function PipelineBuilder({ initialPipelineId }: { initialPipelineId?: string } = {}) {
  const qc = useQueryClient()
  const navigate = useNavigate()

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
    mutationFn: startPipelineRun,
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

    setLocalNodes(prev => {
      // SOURCE: only one allowed — sources are the genesis and cannot chain into each other
      if (nt.category === 'source') {
        if (prev.some(n => n.category === 'source')) {
          setAddStepError('A pipeline can only have one source. Remove the existing source first.')
          return prev
        }
        const newNode: PipelineNodeOut = {
          id: crypto.randomUUID(), node_type: nt.node_type, label: nt.display_name,
          config: {}, category: nt.category, position_x: 0, position_y: 0,
        }
        // Source always goes first; connect to current first node if one exists
        if (prev.length > 0) {
          setLocalEdges(edges => [
            ...edges,
            { id: crypto.randomUUID(), source_node_id: newNode.id, target_node_id: prev[0].id, edge_type: 'results' },
          ])
        }
        return [newNode, ...prev]
      }

      const newNode: PipelineNodeOut = {
        id: crypto.randomUUID(), node_type: nt.node_type, label: nt.display_name,
        config: {}, category: nt.category, position_x: 0, position_y: 0,
      }

      // SCORE: if the last node is also a score, make them parallel (share the same predecessor)
      if (nt.category === 'score' && prev.length > 0 && prev[prev.length - 1].category === 'score') {
        const lastScore = prev[prev.length - 1]
        setLocalEdges(edges => {
          // Find what feeds into the existing last score node
          const predecessorEdge = edges.find(e => e.target_node_id === lastScore.id)
          const parallelEdges: PipelineEdgeOut[] = predecessorEdge
            ? [{ id: crypto.randomUUID(), source_node_id: predecessorEdge.source_node_id, target_node_id: newNode.id, edge_type: 'results' }]
            : []
          return [...edges, ...parallelEdges]
        })
        return [...prev, newNode]
      }

      // All others (ENRICH, SCORE after non-SCORE, FILTER): append to end
      if (prev.length > 0) {
        setLocalEdges(edges => [
          ...edges,
          { id: crypto.randomUUID(), source_node_id: prev[prev.length - 1].id, target_node_id: newNode.id, edge_type: 'results' },
        ])
      }
      return [...prev, newNode]
    })
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
    runMutation.mutate(selectedPipelineId)
  }

  const handleDelete = () => {
    if (!selectedPipelineId) return
    deleteMutation.mutate(selectedPipelineId)
  }

  const isRunning = activeRun?.status === 'running'
  const stepRuns = activeRun?.steps ?? []
  const hasSource = localNodes.some(n => n.category === 'source')
  const canRun = !!selectedPipelineId && !isRunning && hasSource
  const noSourceHint = selectedPipelineId && localNodes.length > 0 && !hasSource
  const editingNode = editingNodeId ? localNodes.find(n => n.id === editingNodeId) ?? null : null
  const editingNodeType = editingNode ? nodeTypes.find(t => t.node_type === editingNode.node_type) : null

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
                  onSelect={setEditingNodeId}
                  onRemove={handleRemoveNode}
                  onAdd={handleAddNode}
                  readOnly={isRunning}
                />
                {/* Action buttons pinned below the step list */}
                {noSourceHint && (
                  <div style={{ padding: '4px 10px', fontSize: 10, color: '#facc15', background: '#facc1511', borderTop: '1px solid #facc1533' }}>
                    Add a source step before running
                  </div>
                )}
                {addStepError && (
                  <div style={{ padding: '4px 10px', fontSize: 10, color: '#f87171', background: '#ef444411', borderTop: '1px solid #ef444433' }}>
                    {addStepError}
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
                      disabled={!dirty}
                      style={{ flex: 1, padding: '5px 0', fontSize: 11, background: dirty ? '#1e293b' : 'transparent', border: '1px solid #334155', borderRadius: 4, color: dirty ? '#e2e8f0' : '#475569', cursor: dirty ? 'pointer' : 'default' }}
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
            />
          )}
        </div>
      </div>
    </div>
  )
}
