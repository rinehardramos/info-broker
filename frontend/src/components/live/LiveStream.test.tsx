import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

vi.mock('../../hooks/useWebSocket', () => ({ useWebSocket: vi.fn() }))
// Spread the real module so every export LiveStream calls (getCoreSettings,
// listSessions, getSession, ...) stays defined; override only listJobs.
vi.mock('../../api/v3', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../api/v3')>()),
  listJobs: vi.fn().mockResolvedValue([
    { id: 'job-1', status: 'completed', query: 'find CTOs', created_at: '2026-04-28T00:00:00Z', completed_at: null, result_count: 5 },
  ]),
}))

import LiveStream from './LiveStream'

function makeClient() {
  // retry:false so any non-overridden query fails fast instead of retrying.
  return new QueryClient({ defaultOptions: { queries: { retry: false } } })
}

describe('LiveStream', () => {
  it('renders Live Stream header', () => {
    render(
      <QueryClientProvider client={makeClient()}>
        <MemoryRouter><LiveStream /></MemoryRouter>
      </QueryClientProvider>,
    )
    expect(screen.getByText(/^live$/i)).toBeInTheDocument()
  })
})
