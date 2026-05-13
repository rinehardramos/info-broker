import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import History from './History'

vi.mock('@/api/v3', () => ({
  listRuns: vi.fn().mockResolvedValue([
    {
      id: 'r1', status: 'succeeded', query: 'investigate: ACME',
      pipeline_name: null, trigger_type: 'investigation',
      created_at: '2026-05-10T10:00:00Z', finished_at: '2026-05-10T10:00:45Z',
    },
    {
      id: 'r2', status: 'failed', query: 'investigate: WIDGETS',
      pipeline_name: null, trigger_type: 'investigation',
      created_at: '2026-05-11T10:00:00Z', finished_at: '2026-05-11T10:01:00Z',
    },
    {
      id: 'r3', status: 'running', query: 'pipeline: media-id',
      pipeline_name: 'media-id', trigger_type: 'pipeline',
      created_at: '2026-05-12T10:00:00Z', finished_at: null,
    },
  ]),
}))

// Mock IconRail (pulls sessionStore which uses localStorage)
vi.mock('@/components/layout/IconRail', () => ({ default: () => null }))

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter><History /></MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('History', () => {
  it('renders all runs by default', async () => {
    renderPage()
    expect(await screen.findByText(/investigate: ACME/)).toBeInTheDocument()
    expect(screen.getByText(/investigate: WIDGETS/)).toBeInTheDocument()
    expect(screen.getByText(/pipeline: media-id/)).toBeInTheDocument()
  })

  it('filters by status', async () => {
    renderPage()
    await screen.findByText(/investigate: ACME/)
    const statusSel = screen.getByLabelText(/status/i) as HTMLSelectElement
    await userEvent.selectOptions(statusSel, 'failed')
    await waitFor(() => expect(screen.queryByText(/investigate: ACME/)).not.toBeInTheDocument())
    expect(screen.getByText(/investigate: WIDGETS/)).toBeInTheDocument()
  })

  it('filters by date range (from)', async () => {
    renderPage()
    await screen.findByText(/investigate: ACME/)
    const fromInput = screen.getByLabelText(/from/i)
    await userEvent.type(fromInput, '2026-05-11')
    await waitFor(() => expect(screen.queryByText(/investigate: ACME/)).not.toBeInTheDocument())
    expect(screen.getByText(/investigate: WIDGETS/)).toBeInTheDocument()
  })
})
