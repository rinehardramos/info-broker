import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { SummaryModal } from './SummaryModal'

vi.mock('../../api/pipelines', () => ({
  getPipelineRun: vi.fn(),
}))
vi.mock('../../api/v3', () => ({
  runAnalyzer: vi.fn(),
}))

import { getPipelineRun } from '../../api/pipelines'
import { runAnalyzer } from '../../api/v3'

function renderModal() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <SummaryModal runId="run-1" open onClose={() => {}} />
    </QueryClientProvider>,
  )
}

describe('SummaryModal', () => {
  beforeEach(() => vi.clearAllMocks())

  it('renders a cached analysis instantly with a Regenerate action', async () => {
    ;(getPipelineRun as ReturnType<typeof vi.fn>).mockResolvedValue({
      research: {
        query: 'find properties',
        findings: [{ title: 'F1' }],
        analysis: { insights: ['Prices cluster under P1M'] },
      },
    })
    renderModal()
    expect(await screen.findByText(/Prices cluster under P1M/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /regenerate/i })).toBeInTheDocument()
  })

  it('shows Generate when no analysis is cached and calls runAnalyzer on click', async () => {
    ;(getPipelineRun as ReturnType<typeof vi.fn>).mockResolvedValue({
      research: { query: 'find properties', findings: [{ title: 'F1' }], analysis: null },
    })
    ;(runAnalyzer as ReturnType<typeof vi.fn>).mockResolvedValue({ status: 'analyzing' })
    renderModal()
    const genBtn = await screen.findByRole('button', { name: /generate/i })
    await userEvent.click(genBtn)
    await waitFor(() => expect(runAnalyzer).toHaveBeenCalledTimes(1))
    // findings + runId threaded through to the analyzer
    const args = (runAnalyzer as ReturnType<typeof vi.fn>).mock.calls[0]
    expect(args[0]).toEqual([{ title: 'F1' }]) // items
    expect(args[4]).toBe('run-1') // runId
  })

  it('treats a _status marker as "not yet analyzed" (no stale render)', async () => {
    ;(getPipelineRun as ReturnType<typeof vi.fn>).mockResolvedValue({
      research: { query: 'q', findings: [{ title: 'F1' }], analysis: { _status: 'analyzing' } },
    })
    renderModal()
    // _status marker must not be rendered as a real analysis
    expect(await screen.findByRole('button', { name: /generate/i })).toBeInTheDocument()
  })
})
