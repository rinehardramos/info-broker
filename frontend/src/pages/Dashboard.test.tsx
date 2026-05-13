import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import Dashboard from './Dashboard'

vi.mock('@/components/layout/IconRail', () => ({
  default: () => null,
}))

vi.mock('@/api/v3', () => ({
  listRuns: vi.fn().mockResolvedValue([
    {
      id: 'r1', status: 'succeeded', query: 'investigate: ACME',
      pipeline_name: null, trigger_type: 'investigation',
      created_at: '2026-05-13T10:00:00Z', finished_at: '2026-05-13T10:00:45Z',
    },
  ]),
  getRunMetrics: vi.fn().mockResolvedValue({
    total_runs: 142, runs_today: 24, success_rate: 0.91,
    live_runs: 3, error_count: 2, avg_duration_seconds: 45,
  }),
}))

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter><Dashboard /></MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('Dashboard', () => {
  it('renders four stat cards with values from metrics endpoint', async () => {
    renderPage()
    expect(await screen.findByText('24')).toBeInTheDocument()
    expect(screen.getByText(/91%/)).toBeInTheDocument()
    expect(screen.getByText('3')).toBeInTheDocument()
    expect(screen.getByText('2')).toBeInTheDocument()
  })

  it('renders recent runs table', async () => {
    renderPage()
    await waitFor(() => expect(screen.getByText(/investigate: ACME/)).toBeInTheDocument())
  })
})
