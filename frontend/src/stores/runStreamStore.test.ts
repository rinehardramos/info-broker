import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest'
import { useRunStreamStore } from './runStreamStore'

const reset = () => useRunStreamStore.setState({ runsById: {} })

describe('runStreamStore — upsertCard', () => {
  beforeEach(reset)

  it('creates a card lazily on first upsert', () => {
    useRunStreamStore.getState().upsertCard('run-1', {
      nodeId: 'node-a',
      nodeName: 'web_search',
      status: 'running',
      startedAt: 1000,
    })
    const cards = useRunStreamStore.getState().runsById['run-1'].cards
    expect(cards['node-a'].nodeName).toBe('web_search')
    expect(cards['node-a'].status).toBe('running')
  })

  it('preserves cardOrder insertion order, never re-sorts', () => {
    const s = useRunStreamStore.getState()
    s.upsertCard('run-1', { nodeId: 'b', nodeName: 'b', status: 'running' })
    s.upsertCard('run-1', { nodeId: 'a', nodeName: 'a', status: 'running' })
    expect(useRunStreamStore.getState().runsById['run-1'].cardOrder).toEqual(['b', 'a'])
  })

  it('merges patch without wiping existing fields', () => {
    const s = useRunStreamStore.getState()
    s.upsertCard('run-1', { nodeId: 'n', nodeName: 'crawl', status: 'running', startedAt: 1 })
    s.upsertCard('run-1', { nodeId: 'n', status: 'succeeded', finishedAt: 2, output: { rows: 3 } })
    const card = useRunStreamStore.getState().runsById['run-1'].cards['n']
    expect(card.nodeName).toBe('crawl')
    expect(card.status).toBe('succeeded')
    expect(card.output).toEqual({ rows: 3 })
  })
})

describe('runStreamStore — setRunStatus', () => {
  beforeEach(reset)

  it('sets run status and creates run entry if absent', () => {
    useRunStreamStore.getState().setRunStatus('run-2', 'pipeline', 'succeeded')
    expect(useRunStreamStore.getState().runsById['run-2'].status).toBe('succeeded')
  })

  it('cancels all running/streaming/pending cards on canceled status', () => {
    const s = useRunStreamStore.getState()
    s.upsertCard('run-3', { nodeId: 'x', nodeName: 'x', status: 'running' })
    s.upsertCard('run-3', { nodeId: 'y', nodeName: 'y', status: 'streaming' })
    s.upsertCard('run-3', { nodeId: 'z', nodeName: 'z', status: 'pending' })
    s.setRunStatus('run-3', 'pipeline', 'canceled')
    const { cards } = useRunStreamStore.getState().runsById['run-3']
    expect(cards['x'].status).toBe('canceled')
    expect(cards['y'].status).toBe('canceled')
    expect(cards['z'].status).toBe('canceled')
  })
})

describe('runStreamStore — suggestions', () => {
  beforeEach(reset)

  it('addSuggestion appends and dismissSuggestion marks dismissed', () => {
    const s = useRunStreamStore.getState()
    s.addSuggestion('run-1', {
      id: 'sug-1', kind: 'next-step', action: 'aggregate',
      title: 'Aggregate', createdAt: Date.now(),
    })
    expect(useRunStreamStore.getState().runsById['run-1'].suggestions).toHaveLength(1)
    s.dismissSuggestion('run-1', 'sug-1')
    const dismissed = useRunStreamStore.getState().runsById['run-1'].dismissedSuggestionIds
    expect(dismissed.has('sug-1')).toBe(true)
  })
})

describe('runStreamStore — clearRun', () => {
  beforeEach(reset)

  it('removes run from runsById', () => {
    useRunStreamStore.getState().setRunStatus('run-del', 'pipeline', 'running')
    useRunStreamStore.getState().clearRun('run-del')
    expect(useRunStreamStore.getState().runsById['run-del']).toBeUndefined()
  })
})

describe('runStreamStore — appendStreamChunk', () => {
  beforeEach(reset)
  afterEach(() => { vi.unstubAllGlobals() })

  it('accumulates chunks and sets status to streaming', async () => {
    // Mock requestAnimationFrame to execute synchronously
    const rafCalls: FrameRequestCallback[] = []
    vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => { rafCalls.push(cb); return 0 })

    const s = useRunStreamStore.getState()
    s.upsertCard('run-raf', { nodeId: 'n1', nodeName: 'llm', status: 'running' })
    s.appendStreamChunk('run-raf', 'n1', 'Hello ', 0)
    s.appendStreamChunk('run-raf', 'n1', 'world', 1) // should be buffered (rAF already pending)

    // rAF not yet called — card still at 'running'
    expect(useRunStreamStore.getState().runsById['run-raf'].cards['n1'].status).toBe('running')

    // Flush the rAF
    rafCalls[0](0)

    const card = useRunStreamStore.getState().runsById['run-raf'].cards['n1']
    expect(card.status).toBe('streaming')
    expect(card.preview).toBe('Hello world') // accumulated text
  })
})

describe('runStreamStore — addEdge', () => {
  beforeEach(reset)

  it('appends edge to run', () => {
    useRunStreamStore.getState().addEdge('run-e', { from: 'a', to: 'b', kind: 'injected' })
    const edges = useRunStreamStore.getState().runsById['run-e'].edges
    expect(edges).toHaveLength(1)
    expect(edges[0]).toEqual({ from: 'a', to: 'b', kind: 'injected' })
  })
})
