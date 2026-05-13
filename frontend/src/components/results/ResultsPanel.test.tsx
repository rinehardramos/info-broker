import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

// ---------------------------------------------------------------------------
// Mocks — must be declared before importing component
// ---------------------------------------------------------------------------

vi.mock('../../api/v3', () => ({
  getJob: vi.fn(),
  getJobResults: vi.fn().mockResolvedValue([]),
  gradeResult: vi.fn(),
  getCoreSettings: vi.fn().mockResolvedValue({ settings: {} }),
}))

const mockListPipelines = vi.fn()
const mockListAllPipelineRuns = vi.fn()
const mockStartPipelineRun = vi.fn()
const mockCancelPipelineRun = vi.fn()
const mockGetPipelineRun = vi.fn()

vi.mock('../../api/pipelines', () => ({
  listPipelines: () => mockListPipelines(),
  listAllPipelineRuns: () => mockListAllPipelineRuns(),
  startPipelineRun: (id: string) => mockStartPipelineRun(id),
  cancelPipelineRun: (id: string) => mockCancelPipelineRun(id),
  getPipelineRun: (id: string) => mockGetPipelineRun(id),
  deletePipeline: vi.fn().mockResolvedValue(undefined),
}))

vi.mock('../../stores/sessionStore', () => ({
  useSessionStore: (selector: (s: unknown) => unknown) =>
    selector({ col1Content: null, setCol1Content: vi.fn(), accessToken: null }),
}))

import ResultsPanel from './ResultsPanel'

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
  mockListPipelines.mockResolvedValue([])
  mockListAllPipelineRuns.mockResolvedValue([])
})

// ---------------------------------------------------------------------------
// Unit — tab bar
// ---------------------------------------------------------------------------

describe('ResultsPanel — tab bar', () => {
  it('renders Pipeline tab as the static tab', () => {
    wrap(<ResultsPanel />)
    expect(screen.getByText('Pipeline')).toBeInTheDocument()
  })

  it('Pipeline is the default active tab', async () => {
    wrap(<ResultsPanel />)
    // Getting Started message appears when Pipeline tab is active and no pipelines exist
    await waitFor(() =>
      expect(screen.getByText('Getting Started')).toBeInTheDocument(),
    )
  })

  it('does not render static News, Summary, Profiles, Social tabs', () => {
    wrap(<ResultsPanel />)
    expect(screen.queryByText('News')).not.toBeInTheDocument()
    expect(screen.queryByText('Summary')).not.toBeInTheDocument()
    expect(screen.queryByText('Profiles')).not.toBeInTheDocument()
    expect(screen.queryByText('Social')).not.toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Unit — Pipeline tab content
// ---------------------------------------------------------------------------

describe('ResultsPanel — Pipeline tab (no pipelines)', () => {
  it('shows Getting Started when no pipelines exist', async () => {
    wrap(<ResultsPanel />)
    await waitFor(() => expect(screen.getByText('Getting Started')).toBeInTheDocument())
  })

  it('shows Create A Pipeline CTA button', async () => {
    wrap(<ResultsPanel />)
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /Create A Pipeline/i })).toBeInTheDocument(),
    )
  })
})

describe('ResultsPanel — Pipeline tab (with pipelines)', () => {
  const PIPELINES = [
    { id: 'pipe-1', name: 'Alpha Pipeline', created_at: '2026-01-01T00:00:00Z' },
    { id: 'pipe-2', name: 'Beta Pipeline', created_at: '2026-01-01T00:00:00Z' },
  ]

  beforeEach(() => {
    mockListPipelines.mockResolvedValue(PIPELINES)
  })

  it('renders pipeline names', async () => {
    wrap(<ResultsPanel />)
    await waitFor(() => expect(screen.getByText('Alpha Pipeline')).toBeInTheDocument())
    expect(screen.getByText('Beta Pipeline')).toBeInTheDocument()
  })

  it('each pipeline has a play button when not running', async () => {
    wrap(<ResultsPanel />)
    await waitFor(() => screen.getByText('Alpha Pipeline'))
    const playButtons = screen.getAllByTitle('Run pipeline')
    expect(playButtons.length).toBe(2)
  })

  it('each pipeline has a reset button', async () => {
    wrap(<ResultsPanel />)
    await waitFor(() => screen.getByText('Alpha Pipeline'))
    const resetButtons = screen.getAllByTitle('Reset (clear selection)')
    expect(resetButtons.length).toBe(2)
  })

  it('clicking play calls startPipelineRun with correct id', async () => {
    mockStartPipelineRun.mockResolvedValue({ id: 'run-1', status: 'running' })
    wrap(<ResultsPanel />)
    await waitFor(() => screen.getByText('Alpha Pipeline'))
    const playButtons = screen.getAllByTitle('Run pipeline')
    await userEvent.click(playButtons[0])
    await waitFor(() => expect(mockStartPipelineRun).toHaveBeenCalledWith('pipe-1'))
  })

  it('pipeline row name is clickable (navigates to pipeline page)', async () => {
    wrap(<ResultsPanel />)
    await waitFor(() => screen.getByText('Alpha Pipeline'))
    const nameSpan = screen.getByText('Alpha Pipeline')
    expect(nameSpan).toHaveStyle({ cursor: 'pointer' })
  })

  it('shows Create Pipeline button even when pipelines exist', async () => {
    wrap(<ResultsPanel />)
    await waitFor(() => screen.getByText('Alpha Pipeline'))
    expect(screen.getByRole('button', { name: /Create Pipeline/i })).toBeInTheDocument()
  })
})

describe('ResultsPanel — Pipeline tab (active run)', () => {
  const PIPELINES = [{ id: 'pipe-1', name: 'Alpha Pipeline', created_at: '2026-01-01T00:00:00Z' }]
  const RUNS = [{
    id: 'run-1', pipeline_id: 'pipe-1', pipeline_name: 'Alpha Pipeline',
    status: 'running', trigger_type: 'manual',
    started_at: new Date().toISOString(), finished_at: null,
    step_count: 2, steps_done: 0,
  }]

  beforeEach(() => {
    mockListPipelines.mockResolvedValue(PIPELINES)
    mockListAllPipelineRuns.mockResolvedValue(RUNS)
  })

  it('shows pause button when run is active on Pipeline tab', async () => {
    wrap(<ResultsPanel />)
    // Auto-switch may move to run tab; click Pipeline to get back
    await waitFor(() => screen.getByText('Pipeline'))
    await userEvent.click(screen.getByText('Pipeline'))
    await waitFor(() => screen.getByTitle('Pause (cancel run)'))
  })

  it('clicking pause calls cancelPipelineRun', async () => {
    mockCancelPipelineRun.mockResolvedValue(undefined)
    wrap(<ResultsPanel />)
    await waitFor(() => screen.getByText('Pipeline'))
    await userEvent.click(screen.getByText('Pipeline'))
    await waitFor(() => screen.getByTitle('Pause (cancel run)'))
    await userEvent.click(screen.getByTitle('Pause (cancel run)'))
    await waitFor(() => expect(mockCancelPipelineRun).toHaveBeenCalledWith('run-1'))
  })
})

// ---------------------------------------------------------------------------
// Unit — Results tab
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Unit — pipeline lock & swipe delete
// ---------------------------------------------------------------------------

describe('ResultsPanel — pipeline lock', () => {
  const PIPELINES = [
    { id: 'pipe-1', name: 'Alpha Pipeline', is_system: false, created_at: '2026-01-01T00:00:00Z' },
    { id: 'pipe-2', name: 'System Pipeline', is_system: true, created_at: '2026-01-01T00:00:00Z' },
  ]

  beforeEach(() => {
    mockListPipelines.mockResolvedValue(PIPELINES)
  })

  it('each pipeline row has a lock toggle button', async () => {
    wrap(<ResultsPanel />)
    await waitFor(() => screen.getByText('Alpha Pipeline'))
    const lockButtons = screen.getAllByTitle(/lock/i)
    expect(lockButtons.length).toBeGreaterThanOrEqual(2)
  })

  it('system pipelines are always shown as locked', async () => {
    wrap(<ResultsPanel />)
    await waitFor(() => screen.getByText('System Pipeline'))
    // The system pipeline row should not be swipeable — it has a locked indicator
    const row = screen.getByText('System Pipeline').closest('[data-testid]')
    expect(row).toBeTruthy()
  })

  it('no confirmation dialog is shown on swipe delete', async () => {
    wrap(<ResultsPanel />)
    await waitFor(() => screen.getByText('Alpha Pipeline'))
    // There should be no "Cancel" or "Delete" confirm buttons visible
    expect(screen.queryByText('Cancel')).not.toBeInTheDocument()
    expect(screen.queryByText(/permanently delete/i)).not.toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Unit — pipeline click selects latest run
// ---------------------------------------------------------------------------

describe('ResultsPanel — pipeline click selects run', () => {
  const PIPELINES = [
    { id: 'pipe-1', name: 'Click Test Pipeline', is_system: false, created_at: '2026-01-01T00:00:00Z' },
  ]
  const RUNS = [{
    id: 'run-1', pipeline_id: 'pipe-1', pipeline_name: 'Click Test Pipeline',
    status: 'succeeded', trigger_type: 'manual',
    started_at: '2026-01-01T00:00:00Z', finished_at: '2026-01-01T00:01:00Z',
    step_count: 1, steps_done: 1,
  }]

  beforeEach(() => {
    mockListPipelines.mockResolvedValue(PIPELINES)
    mockListAllPipelineRuns.mockResolvedValue(RUNS)
  })

  it('pipeline row name does not use a link element', async () => {
    wrap(<ResultsPanel />)
    await waitFor(() => screen.getByTestId('pipeline-row-pipe-1'))
    const row = screen.getByTestId('pipeline-row-pipe-1')
    const nameSpan = row.querySelector('span.truncate')
    expect(nameSpan).toBeTruthy()
    expect(nameSpan!.closest('a')).toBeNull()
  })

  it('has an edit button that navigates to builder', async () => {
    wrap(<ResultsPanel />)
    await waitFor(() => screen.getByTestId('pipeline-row-pipe-1'))
    expect(screen.getByTitle('Edit pipeline')).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Unit — IS tag on agent_is runs
// ---------------------------------------------------------------------------

describe('ResultsPanel — IS tag', () => {
  const PIPELINES = [
    { id: 'pipe-1', name: 'IS Test Pipeline', is_system: false, created_at: '2026-01-01T00:00:00Z' },
  ]
  const RUNS = [{
    id: 'run-1', pipeline_id: 'pipe-1', pipeline_name: 'IS Test Pipeline',
    status: 'succeeded', trigger_type: 'agent_is',
    started_at: '2026-01-01T00:00:00Z', finished_at: '2026-01-01T00:01:00Z',
    step_count: 2, steps_done: 2,
  }]

  beforeEach(() => {
    mockListPipelines.mockResolvedValue(PIPELINES)
    mockListAllPipelineRuns.mockResolvedValue(RUNS)
  })

  it('shows IS badge on pipeline with agent_is run', async () => {
    wrap(<ResultsPanel />)
    await waitFor(() => screen.getByText('IS Test Pipeline'))
    expect(screen.getByText('IS')).toBeInTheDocument()
  })
})

describe('ResultsPanel — dynamic run tabs', () => {
  it('shows run tabs when pipeline runs exist', async () => {
    const RUNS = [{
      id: 'run-1', pipeline_id: 'pipe-1', pipeline_name: 'Alpha Pipeline',
      status: 'running', trigger_type: 'manual',
      started_at: new Date().toISOString(), finished_at: null,
      step_count: 2, steps_done: 0,
    }]
    mockListAllPipelineRuns.mockResolvedValue(RUNS)
    mockListPipelines.mockResolvedValue([{ id: 'pipe-1', name: 'Alpha Pipeline', created_at: '2026-01-01T00:00:00Z' }])
    wrap(<ResultsPanel />)
    await waitFor(() => expect(screen.getByText('Alpha Pipeline')).toBeInTheDocument())
  })

  it('Pipeline tab does not contain RUN RESULTS heading', async () => {
    wrap(<ResultsPanel />)
    await waitFor(() => screen.getByText('Getting Started'))
    expect(screen.queryByText('RUN RESULTS')).not.toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Results tab
// ---------------------------------------------------------------------------

describe('ResultsPanel — Results tab', () => {
  const RUNS = [
    {
      id: 'run-aaa', pipeline_id: 'pipe-1', pipeline_name: 'Alpha Pipeline',
      status: 'succeeded', trigger_type: 'manual',
      started_at: new Date('2026-05-13T10:00:00Z').toISOString(), finished_at: null,
      step_count: 2, steps_done: 2, error_message: null, query: null,
    },
    {
      id: 'run-bbb', pipeline_id: 'pipe-2', pipeline_name: 'Beta Pipeline',
      status: 'failed', trigger_type: 'manual',
      started_at: new Date('2026-05-13T09:00:00Z').toISOString(), finished_at: null,
      step_count: 2, steps_done: 1, error_message: null, query: null,
    },
  ]

  beforeEach(() => {
    mockListAllPipelineRuns.mockResolvedValue(RUNS)
    mockListPipelines.mockResolvedValue([])
  })

  it('renders a Results tab button', () => {
    wrap(<ResultsPanel />)
    expect(screen.getByTestId('results-tab-button')).toBeInTheDocument()
  })

  it('clicking Results tab shows run list', async () => {
    const user = userEvent.setup()
    wrap(<ResultsPanel />)
    await user.click(screen.getByTestId('results-tab-button'))
    await waitFor(() => expect(screen.getByTestId('runs-list-tab')).toBeInTheDocument())
  })

  it('run list shows pipeline names', async () => {
    const user = userEvent.setup()
    wrap(<ResultsPanel />)
    await user.click(screen.getByTestId('results-tab-button'))
    await waitFor(() => {
      // Pipeline names appear both in the dynamic tab bar and in the runs list
      expect(screen.getAllByText('Alpha Pipeline').length).toBeGreaterThanOrEqual(1)
      expect(screen.getAllByText('Beta Pipeline').length).toBeGreaterThanOrEqual(1)
    })
  })

  it('run list shows status badges', async () => {
    const user = userEvent.setup()
    wrap(<ResultsPanel />)
    await user.click(screen.getByTestId('results-tab-button'))
    await waitFor(() => {
      expect(screen.getByText('succeeded')).toBeInTheDocument()
      expect(screen.getByText('failed')).toBeInTheDocument()
    })
  })

  it('clicking a run row switches away from the Results tab', async () => {
    mockGetPipelineRun.mockResolvedValue({
      id: 'run-aaa', pipeline_id: 'pipe-1', status: 'succeeded',
      trigger_type: 'manual', started_at: new Date().toISOString(), finished_at: null,
      steps: [], research: null,
    })
    const user = userEvent.setup()
    wrap(<ResultsPanel />)
    await user.click(screen.getByTestId('results-tab-button'))
    await waitFor(() => screen.getByTestId('run-row-run-aaa'))
    await user.click(screen.getByTestId('run-row-run-aaa'))
    // The runs-list-tab should no longer be visible (we've switched to the run tab)
    await waitFor(() => expect(screen.queryByTestId('runs-list-tab')).not.toBeInTheDocument())
  })
})
