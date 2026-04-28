import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

vi.mock('../../hooks/useWebSocket', () => ({ useWebSocket: vi.fn() }))
vi.mock('../../api/v3', () => ({
  listJobs: vi.fn().mockResolvedValue([
    { id: 'job-1', status: 'completed', query: 'find CTOs', created_at: '2026-04-28T00:00:00Z', completed_at: null, result_count: 5 },
  ]),
}))

import LiveStream from './LiveStream'

describe('LiveStream', () => {
  it('renders Live Stream header', () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter><LiveStream /></MemoryRouter>
      </QueryClientProvider>,
    )
    expect(screen.getByText('Live')).toBeInTheDocument()
  })
})
