import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

vi.mock('../../api/v3', () => ({
  sendMessage: vi.fn().mockResolvedValue({ job_id: 'test-job-1', status: 'pending' }),
}))
vi.mock('../../hooks/useWebSocket', () => ({ useWebSocket: vi.fn() }))

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

  it('sends message and shows user bubble', async () => {
    const { sendMessage } = await import('../../api/v3')
    wrap(<AgentChat />)
    const input = screen.getByPlaceholderText(/ask/i)
    fireEvent.change(input, { target: { value: 'find CTOs in Manila' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    await waitFor(() => {
      expect(sendMessage).toHaveBeenCalledWith('find CTOs in Manila', undefined)
    })
    expect(screen.getByText('find CTOs in Manila')).toBeInTheDocument()
  })
})
