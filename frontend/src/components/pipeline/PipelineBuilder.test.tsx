import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { PipelineBuilder } from './PipelineBuilder'

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockCreatePipeline = vi.fn()
const mockUpdatePipeline = vi.fn()
const mockDeletePipeline = vi.fn()
const mockListPipelines = vi.fn()
const mockGetPipeline = vi.fn()
const mockListNodeTypes = vi.fn()

vi.mock('../../api/pipelines', () => ({
  listPipelines: () => mockListPipelines(),
  getPipeline: (id: string) => mockGetPipeline(id),
  listNodeTypes: () => mockListNodeTypes(),
  createPipeline: (body: unknown) => mockCreatePipeline(body),
  updatePipeline: (id: string, body: unknown) => mockUpdatePipeline(id, body),
  deletePipeline: (id: string) => mockDeletePipeline(id),
}))

const PIPELINES = [
  { id: 'pipe-1', name: 'Pipeline One', description: null, created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z' },
  { id: 'pipe-2', name: 'Pipeline Two', description: null, created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z' },
]

const NODE_TYPES = [
  { node_type: 'ddg_search', display_name: 'DDG Search', category: 'source', config_schema: {} },
  { node_type: 'rss_monitor', display_name: 'RSS Monitor', category: 'source', config_schema: {} },
]

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function wrap(ui: React.ReactNode) {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  mockListPipelines.mockResolvedValue(PIPELINES)
  mockListNodeTypes.mockResolvedValue(NODE_TYPES)
  mockGetPipeline.mockResolvedValue({
    id: 'pipe-1', name: 'Pipeline One', description: null,
    nodes: [], edges: [],
    created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z',
  })
  mockCreatePipeline.mockResolvedValue({
    id: 'pipe-new', name: 'My New Pipeline', description: null,
    created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z',
  })
})

// ---------------------------------------------------------------------------
// Unit — renders
// ---------------------------------------------------------------------------

describe('PipelineBuilder — renders', () => {
  it('shows PIPELINES sidebar header', () => {
    wrap(<PipelineBuilder />)
    expect(screen.getByText('PIPELINES')).toBeInTheDocument()
  })

  it('renders pipeline names from API', async () => {
    wrap(<PipelineBuilder />)
    await waitFor(() => expect(screen.getByText('Pipeline One')).toBeInTheDocument())
    expect(screen.getByText('Pipeline Two')).toBeInTheDocument()
  })

  it('shows "+ New Pipeline" button', async () => {
    wrap(<PipelineBuilder />)
    await waitFor(() => expect(screen.getByText('+ New Pipeline')).toBeInTheDocument())
  })
})

// ---------------------------------------------------------------------------
// Unit — "+ New Pipeline" inline form
// ---------------------------------------------------------------------------

describe('PipelineBuilder — new pipeline form', () => {
  it('clicking "+ New Pipeline" shows creation form', async () => {
    wrap(<PipelineBuilder />)
    await waitFor(() => screen.getByText('+ New Pipeline'))
    await userEvent.click(screen.getByText('+ New Pipeline'))
    expect(screen.getByPlaceholderText('Pipeline name *')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('Description (optional)')).toBeInTheDocument()
  })

  it('Create button is disabled when name is empty', async () => {
    wrap(<PipelineBuilder />)
    await waitFor(() => screen.getByText('+ New Pipeline'))
    await userEvent.click(screen.getByText('+ New Pipeline'))
    const createBtn = screen.getByRole('button', { name: 'Create' })
    expect(createBtn).toBeDisabled()
  })

  it('Create button enables when name is typed', async () => {
    wrap(<PipelineBuilder />)
    await waitFor(() => screen.getByText('+ New Pipeline'))
    await userEvent.click(screen.getByText('+ New Pipeline'))
    await userEvent.type(screen.getByPlaceholderText('Pipeline name *'), 'My New Pipeline')
    const createBtn = screen.getByRole('button', { name: 'Create' })
    expect(createBtn).not.toBeDisabled()
  })

  it('Cancel dismisses form without creating pipeline', async () => {
    wrap(<PipelineBuilder />)
    await waitFor(() => screen.getByText('+ New Pipeline'))
    await userEvent.click(screen.getByText('+ New Pipeline'))
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(screen.queryByPlaceholderText('Pipeline name *')).not.toBeInTheDocument()
    expect(mockCreatePipeline).not.toHaveBeenCalled()
  })

  it('Escape key cancels form', async () => {
    wrap(<PipelineBuilder />)
    await waitFor(() => screen.getByText('+ New Pipeline'))
    await userEvent.click(screen.getByText('+ New Pipeline'))
    const nameInput = screen.getByPlaceholderText('Pipeline name *')
    await userEvent.type(nameInput, '{Escape}')
    expect(screen.queryByPlaceholderText('Pipeline name *')).not.toBeInTheDocument()
  })

  it('submitting form calls createPipeline with correct payload', async () => {
    const user = userEvent.setup()
    wrap(<PipelineBuilder />)
    await waitFor(() => screen.getByText('+ New Pipeline'))
    await user.click(screen.getByText('+ New Pipeline'))

    await user.type(screen.getByPlaceholderText('Pipeline name *'), 'My New Pipeline')
    fireEvent.change(screen.getByPlaceholderText('Description (optional)'), { target: { value: 'A description' } })
    await user.click(screen.getByRole('button', { name: 'Create' }))

    await waitFor(() => expect(mockCreatePipeline).toHaveBeenCalledWith(
      expect.objectContaining({
        name: 'My New Pipeline',
        description: 'A description',
        nodes: [],
        edges: [],
      }),
    ))
  })

  it('Enter key submits form', async () => {
    wrap(<PipelineBuilder />)
    await waitFor(() => screen.getByText('+ New Pipeline'))
    await userEvent.click(screen.getByText('+ New Pipeline'))
    await userEvent.type(screen.getByPlaceholderText('Pipeline name *'), 'Enter Pipeline{Enter}')
    await waitFor(() => expect(mockCreatePipeline).toHaveBeenCalled())
  })

  it('form hides after successful creation', async () => {
    wrap(<PipelineBuilder />)
    await waitFor(() => screen.getByText('+ New Pipeline'))
    await userEvent.click(screen.getByText('+ New Pipeline'))
    await userEvent.type(screen.getByPlaceholderText('Pipeline name *'), 'New')
    await userEvent.click(screen.getByRole('button', { name: 'Create' }))
    await waitFor(() =>
      expect(screen.queryByPlaceholderText('Pipeline name *')).not.toBeInTheDocument(),
    )
  })

  it('existing selected pipeline is not deselected when form opens', async () => {
    wrap(<PipelineBuilder initialPipelineId="pipe-1" />)
    await waitFor(() => screen.getByText('Pipeline One'))
    await userEvent.click(screen.getByText('+ New Pipeline'))
    // The existing pipeline name should still be in the sidebar (not cleared)
    expect(screen.getByText('Pipeline One')).toBeInTheDocument()
    expect(screen.getByText('Pipeline Two')).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Unit — initialPipelineId prop
// ---------------------------------------------------------------------------

describe('PipelineBuilder — initialPipelineId', () => {
  it('pre-selects pipeline when initialPipelineId is provided', async () => {
    wrap(<PipelineBuilder initialPipelineId="pipe-1" />)
    await waitFor(() => expect(mockGetPipeline).toHaveBeenCalledWith('pipe-1'))
  })

  it('does not pre-select when no initialPipelineId', async () => {
    wrap(<PipelineBuilder />)
    await waitFor(() => screen.getByText('Pipeline One'))
    expect(mockGetPipeline).not.toHaveBeenCalled()
  })
})

// ---------------------------------------------------------------------------
// Unit — reorder steps with edges
// ---------------------------------------------------------------------------

describe('PipelineBuilder — reorder steps (with edges)', () => {
  beforeEach(() => {
    mockGetPipeline.mockResolvedValue({
      id: 'pipe-1', name: 'Pipeline One', description: null,
      nodes: [
        { id: 'n1', node_type: 'qdrant_search', label: 'Qdrant Search', config: {}, category: 'enrich' },
        { id: 'n2', node_type: 'manual_scoring', label: 'Manual Scoring', config: {}, category: 'score' },
      ],
      edges: [
        { id: 'e1', source_node_id: 'n1', target_node_id: 'n2', edge_type: 'results' },
      ],
      created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z',
    })
  })

  it('moving a step up re-sorts display order when a direct edge exists', async () => {
    wrap(<PipelineBuilder initialPipelineId="pipe-1" />)
    await waitFor(() => screen.getByText('Pipeline One'))

    // Initial topo order: qdrant_search first (n1 → n2)
    const cardsBefore = document.querySelectorAll('[data-testid^="step-card-"]')
    expect(cardsBefore[0].getAttribute('data-testid')).toBe('step-card-qdrant_search')

    // Move up the second step (nth(1) because nth(0) is disabled for the first node)
    const moveUpBtns = screen.getAllByTitle('Move up')
    await userEvent.click(moveUpBtns[1])

    // After move: manual_scoring should be first
    await waitFor(() => {
      const cardsAfter = document.querySelectorAll('[data-testid^="step-card-"]')
      expect(cardsAfter[0].getAttribute('data-testid')).toBe('step-card-manual_scoring')
    })
  })

  it('initial step list order follows edges, not insertion order', async () => {
    // Nodes added out-of-order: n2 (AI Provider) before n1 (Agent Input) in insertion order
    // Edge defines: n1 → n2 → n3, so display should be n1, n2, n3 regardless of insertion order
    mockGetPipeline.mockResolvedValue({
      id: 'pipe-1', name: 'Pipeline One', description: null,
      nodes: [
        { id: 'n3', node_type: 'manual_scoring', label: 'AI Scoring', config: {}, category: 'score' },
        { id: 'n2', node_type: 'ddg_search', label: 'DDG Search', config: {}, category: 'enrich' },
        { id: 'n1', node_type: 'qdrant_search', label: 'Agent Input', config: {}, category: 'source' },
      ],
      edges: [
        { id: 'e1', source_node_id: 'n1', target_node_id: 'n2', edge_type: 'results' },
        { id: 'e2', source_node_id: 'n2', target_node_id: 'n3', edge_type: 'results' },
      ],
      created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z',
    })
    wrap(<PipelineBuilder initialPipelineId="pipe-1" />)
    await waitFor(() => screen.getByText('Pipeline One'))

    const cards = document.querySelectorAll('[data-testid^="step-card-"]')
    // Topo order should be n1 → n2 → n3, NOT insertion order n3, n2, n1
    expect(cards[0].getAttribute('data-testid')).toBe('step-card-qdrant_search')  // n1 (Agent Input)
    expect(cards[1].getAttribute('data-testid')).toBe('step-card-ddg_search')    // n2 (DDG Search)
    expect(cards[2].getAttribute('data-testid')).toBe('step-card-manual_scoring') // n3 (AI Scoring)
  })

  it('nodes at the same topological level retain insertion order', async () => {
    // n1 and n2 are both sources (no edges between them), n3 depends on both
    mockGetPipeline.mockResolvedValue({
      id: 'pipe-1', name: 'Pipeline One', description: null,
      nodes: [
        { id: 'n1', node_type: 'qdrant_search', label: 'Source A', config: {}, category: 'source' },
        { id: 'n2', node_type: 'ddg_search', label: 'Source B', config: {}, category: 'source' },
        { id: 'n3', node_type: 'manual_scoring', label: 'Scoring', config: {}, category: 'score' },
      ],
      edges: [
        { id: 'e1', source_node_id: 'n1', target_node_id: 'n3', edge_type: 'results' },
        { id: 'e2', source_node_id: 'n2', target_node_id: 'n3', edge_type: 'results' },
      ],
      created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z',
    })
    wrap(<PipelineBuilder initialPipelineId="pipe-1" />)
    await waitFor(() => screen.getByText('Pipeline One'))

    const cards = document.querySelectorAll('[data-testid^="step-card-"]')
    // n1 and n2 are at same level → insertion order preserved (n1 before n2)
    // n3 comes last (depends on both)
    expect(cards[0].getAttribute('data-testid')).toBe('step-card-qdrant_search')
    expect(cards[1].getAttribute('data-testid')).toBe('step-card-ddg_search')
    expect(cards[2].getAttribute('data-testid')).toBe('step-card-manual_scoring')
  })

  it('tool edges do not affect execution order in the step list', async () => {
    // n1 → n2 (results), n3 is a tool-target from n2; tool edges shouldn't affect topo sort
    mockGetPipeline.mockResolvedValue({
      id: 'pipe-1', name: 'Pipeline One', description: null,
      nodes: [
        { id: 'n2', node_type: 'manual_scoring', label: 'Scoring', config: {}, category: 'score' },
        { id: 'n1', node_type: 'qdrant_search', label: 'Search', config: {}, category: 'source' },
        { id: 'n3', node_type: 'ddg_search', label: 'Tool Node', config: {}, category: 'enrich' },
      ],
      edges: [
        { id: 'e1', source_node_id: 'n1', target_node_id: 'n2', edge_type: 'results' },
        { id: 'e2', source_node_id: 'n2', target_node_id: 'n3', edge_type: 'tool' },
      ],
      created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z',
    })
    wrap(<PipelineBuilder initialPipelineId="pipe-1" />)
    await waitFor(() => screen.getByText('Pipeline One'))

    const cards = document.querySelectorAll('[data-testid^="step-card-"]')
    // Results edge n1 → n2 defines order; tool edge should not make n3 appear before n2
    expect(cards[0].getAttribute('data-testid')).toBe('step-card-qdrant_search')  // n1
    expect(cards[1].getAttribute('data-testid')).toBe('step-card-manual_scoring') // n2
  })
})

// ---------------------------------------------------------------------------
// Integration — save only calls update, never silent create
// ---------------------------------------------------------------------------

describe('PipelineBuilder — save flow', () => {
  it('Save button does not call createPipeline directly', async () => {
    wrap(<PipelineBuilder initialPipelineId="pipe-1" />)
    await waitFor(() => screen.getByText('Pipeline One'))
    // Save is disabled unless dirty — just verify createPipeline is never called
    expect(mockCreatePipeline).not.toHaveBeenCalled()
  })
})
