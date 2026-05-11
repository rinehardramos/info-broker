import { useState, useRef, useEffect, useMemo, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  listPipelines, getPipeline, listNodeTypes, createPipeline, updatePipeline,
  deletePipeline,
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
  // Refs to hold latest state — handleSave may be called before React applies queued updates
  const nodesRef = useRef(localNodes)
  const edgesRef = useRef(localEdges)
  const nameRef = useRef(localName)
  const descRef = useRef(localDesc)
  nodesRef.current = localNodes
  edgesRef.current = localEdges
  nameRef.current = localName
  descRef.current = localDesc
  const [editingNodeId, setEditingNodeId] = useState<string | null>(null)
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

  const isSystemPipeline = pipelineDetail?.is_system ?? false
  const isAgentPipeline = localNodes.some(n => n.node_type === 'agent_input')
  const agentInputNode = localNodes.find(n => n.node_type === 'agent_input')
  const lockedNodeIds = isAgentPipeline && agentInputNode
    ? new Set([agentInputNode.id])
    : new Set<string>()
  const hiddenCategories = isAgentPipeline ? new Set(['source']) : new Set<string>()

  // Sort nodes by topological order derived from edges so the step list numbers
  // match the DAG execution order. Nodes at the same topological depth retain
  // their relative insertion order (allowing move-up/down for unconnected nodes).
  const topoSortedNodes = useMemo(() => {
    // Only results edges affect execution order; tool edges are config-only
    const resultEdges = localEdges.filter(e => e.edge_type !== 'tool')
    if (resultEdges.length === 0) return localNodes
    const inDegree = new Map(localNodes.map(n => [n.id, 0]))
    const adj = new Map(localNodes.map(n => [n.id, [] as string[]]))
    for (const e of resultEdges) {
      inDegree.set(e.target_node_id, (inDegree.get(e.target_node_id) ?? 0) + 1)
      adj.get(e.source_node_id)?.push(e.target_node_id)
    }
    const nodeMap = new Map(localNodes.map(n => [n.id, n]))
    const queue = localNodes.filter(n => (inDegree.get(n.id) ?? 0) === 0)
    const sorted: PipelineNodeOut[] = []
    while (queue.length > 0) {
      const node = queue.shift()!
      sorted.push(node)
      for (const tid of adj.get(node.id) ?? []) {
        const deg = (inDegree.get(tid) ?? 1) - 1
        inDegree.set(tid, deg)
        if (deg === 0) { const t = nodeMap.get(tid); if (t) queue.push(t) }
      }
    }
    const sortedIds = new Set(sorted.map(n => n.id))
    return [...sorted, ...localNodes.filter(n => !sortedIds.has(n.id))]
  }, [localNodes, localEdges])

  const handleAddNode = (nodeType: string) => {
    const nt = nodeTypes.find(t => t.node_type === nodeType)
    if (!nt) return
    setAddStepError(null)

    // Datastore nodes are tool-only — add without auto-chaining edges
    if (nt.category === 'datastore') {
      const newNode: PipelineNodeOut = {
        id: crypto.randomUUID(), node_type: nt.node_type, label: nt.display_name,
        config: {}, category: nt.category, position_x: 0, position_y: 0,
      }
      setLocalNodes(prev => [...prev, newNode])
      setDirty(true)
      return
    }

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
    if (lockedNodeIds.has(nodeId)) return
    setLocalNodes(prev => prev.filter(n => n.id !== nodeId))
    setLocalEdges(prev => prev.filter(e => e.source_node_id !== nodeId && e.target_node_id !== nodeId))
    if (editingNodeId === nodeId) setEditingNodeId(null)
    setDirty(true)
  }

  const handleConfigChange = (nodeId: string, config: Record<string, unknown>) => {
    setLocalNodes(prev => {
      const next = prev.map(n => n.id === nodeId ? { ...n, config } : n)
      nodesRef.current = next  // Update ref immediately for handleSave
      return next
    })
    setDirty(true)
  }

  const handleMoveNode = (nodeId: string, direction: 'up' | 'down') => {
    // Operate on the displayed (topo-sorted) order so the user sees consistent behaviour
    const dispIdx = topoSortedNodes.findIndex(n => n.id === nodeId)
    if (dispIdx === -1) return
    const swapDispIdx = direction === 'up' ? dispIdx - 1 : dispIdx + 1
    if (swapDispIdx < 0 || swapDispIdx >= topoSortedNodes.length) return

    const displaced = topoSortedNodes[swapDispIdx]
    const moved     = topoSortedNodes[dispIdx]

    // Swap insertion order to match the new display order
    const next = [...localNodes]
    const la = next.findIndex(n => n.id === displaced.id)
    const lb = next.findIndex(n => n.id === moved.id)
    ;[next[la], next[lb]] = [next[lb], next[la]]
    setLocalNodes(next)

    // Reverse any direct edge between the two swapped nodes so topo sort
    // reflects the user's intended order after the move
    setLocalEdges(prev => prev.map(e => {
      if (e.source_node_id === displaced.id && e.target_node_id === moved.id)
        return { ...e, source_node_id: moved.id, target_node_id: displaced.id }
      if (e.source_node_id === moved.id && e.target_node_id === displaced.id)
        return { ...e, source_node_id: displaced.id, target_node_id: moved.id }
      return e
    }))
    setDirty(true)
  }

  const handleEdgeChange = (sourceId: string, targetId: string, connected: boolean) => {
    if (connected) {
      const newEdge: PipelineEdgeOut = {
        id: crypto.randomUUID(),
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

  const handleToolEdgeChange = (sourceId: string, targetId: string, connected: boolean) => {
    if (connected) {
      const newEdge: PipelineEdgeOut = {
        id: crypto.randomUUID(),
        source_node_id: sourceId,
        target_node_id: targetId,
        edge_type: 'tool',
      }
      setLocalEdges(prev => [...prev, newEdge])
    } else {
      setLocalEdges(prev => prev.filter(
        e => !(e.source_node_id === sourceId && e.target_node_id === targetId && e.edge_type === 'tool')
      ))
    }
    setDirty(true)
  }

  const handleSave = useCallback(() => {
    if (!selectedPipelineId) return
    // Read from refs to avoid stale closure — onChange may have called
    // setLocalNodes but React hasn't applied the update yet.
    updateMutation.mutate({
      id: selectedPipelineId,
      body: {
        name: nameRef.current,
        description: descRef.current || null,
        nodes: nodesRef.current.map(n => ({
          id: n.id,
          node_type: n.node_type,
          label: n.label,
          config: n.config,
          position_x: n.position_x,
          position_y: n.position_y,
        })),
        edges: edgesRef.current.map(e => ({
          source_node_id: e.source_node_id,
          target_node_id: e.target_node_id,
          edge_type: e.edge_type,
        })),
      },
    })
  }, [selectedPipelineId, updateMutation])

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

  const handleDelete = () => {
    if (!selectedPipelineId) return
    deleteMutation.mutate(selectedPipelineId)
  }

  const sourceCount = localNodes.filter(n => n.category === 'source' && n.node_type !== 'aggregator').length
  const hasAggregator = localNodes.some(n => n.node_type === 'aggregator')
  const needsAggregator = sourceCount > 1 && !hasAggregator
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
  const canSave = !!selectedPipelineId && invalidCount === 0


  return (
    <div style={{ display: 'flex', height: '100%', background: '#0d1117', color: '#e2e8f0', overflow: 'hidden' }}>
      {/* Saved pipelines sidebar */}
      <div style={{ width: 180, borderRight: '1px solid #1e293b', display: 'flex', flexDirection: 'column' }}>
        <div style={{ padding: '8px', borderBottom: '1px solid #1e293b', fontSize: 11, color: '#94a3b8' }}>PIPELINES</div>
        <div style={{ flex: 1, overflowY: 'auto' }}>
          {pipelines.map(p => (
            <div
              key={p.id}
              onClick={() => { setSelectedPipelineId(p.id); setCreatingNew(false); navigate(`/pipelines/${p.id}`, { replace: true }) }}
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
          {isSystemPipeline && (
            <span
              style={{
                fontSize: 9,
                padding: '1px 5px',
                borderRadius: 3,
                background: '#1e3a5f',
                color: '#60a5fa',
                border: '1px solid #2d5a8f',
                fontWeight: 600,
                marginLeft: 4,
              }}
            >
              DEFAULT
            </span>
          )}
        </div>

        {/* Resizable panels */}
        <div style={{ flex: 1, position: 'relative', overflow: 'hidden' }}>
          <ResizableSplit
            left={
              <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
                <StepList
                  nodes={topoSortedNodes}
                  nodeTypes={nodeTypes}
                  selectedNodeId={editingNodeId}
                  invalidNodeIds={invalidNodeIds}
                  lockedNodeIds={lockedNodeIds}
                  toolNodeIds={new Set(localEdges.filter(e => e.edge_type === 'tool').map(e => e.target_node_id))}
                  hiddenCategories={hiddenCategories}
                  onSelect={setEditingNodeId}
                  onRemove={handleRemoveNode}
                  onMoveUp={id => handleMoveNode(id, 'up')}
                  onMoveDown={id => handleMoveNode(id, 'down')}
                  onAdd={handleAddNode}
                  readOnly={isSystemPipeline}
                />
                {/* Action buttons pinned below the step list */}
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
                {confirmDelete && !isSystemPipeline ? (
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
                      disabled={!canSave || isSystemPipeline}
                      style={{
                        flex: 1, padding: '5px 0', fontSize: 11,
                        background: (canSave && !isSystemPipeline) ? (dirty ? '#1e3a5f' : '#1e293b') : 'transparent',
                        border: `1px solid ${(canSave && !isSystemPipeline) ? (dirty ? '#60a5fa' : '#334155') : '#1e293b'}`,
                        borderRadius: 4,
                        color: (canSave && !isSystemPipeline) ? '#e2e8f0' : '#475569',
                        cursor: (canSave && !isSystemPipeline) ? 'pointer' : 'default',
                      }}
                    >
                      Save{dirty ? ' *' : ''}
                    </button>
                    {selectedPipelineId && !isSystemPipeline && (
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
              <DagPreview nodes={localNodes} edges={localEdges} />
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
              onToolEdgeChange={handleToolEdgeChange}
            />
          )}
        </div>
      </div>
    </div>
  )
}
