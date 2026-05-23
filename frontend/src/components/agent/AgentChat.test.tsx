import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

vi.mock('../../api/v3', () => ({
  sendMessage: vi.fn().mockResolvedValue({ job_id: 'test-job-1', status: 'pending' }),
  getBrainStatus: vi.fn().mockResolvedValue({ status: 'ok' }),
  archiveSession: vi.fn().mockResolvedValue({}),
  listSessions: vi.fn().mockResolvedValue([]),
  getSession: vi.fn().mockResolvedValue(null),
  listModes: vi.fn().mockResolvedValue([]),
}))
vi.mock('../../hooks/useWebSocket', () => ({ useWebSocket: vi.fn() }))
vi.mock('@/api/brain', () => ({ brainApi: { injectNode: vi.fn() } }))
vi.mock('@/components/preflight', () => ({
  PreflightPanel: () => null,
}))
vi.mock('@/components/results/BrainSuggestionBanner', () => ({
  BrainSuggestionBanner: () => null,
}))

import AgentChat from './AgentChat'

function wrap(ui: React.ReactNode) {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('AgentChat', () => {
  it('renders message input', () => {
    wrap(<AgentChat />)
    expect(screen.getByPlaceholderText(/ask/i)).toBeInTheDocument()
  })

  it('accepts user input in the textarea', () => {
    // Smoke-test that the textarea is controlled and reflects typed input.
    wrap(<AgentChat />)
    const textarea = screen.getByPlaceholderText(/ask.*info-broker/i)
    fireEvent.change(textarea, { target: { value: 'find CTOs in Manila' } })
    expect((textarea as HTMLTextAreaElement).value).toBe('find CTOs in Manila')
  })
})
