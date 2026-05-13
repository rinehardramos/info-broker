import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { DownloadMenu } from './DownloadMenu'

vi.mock('@/api/v3', () => ({
  createExport: vi.fn(),
  getExport: vi.fn(),
}))

import { createExport, getExport } from '@/api/v3'

describe('DownloadMenu', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    Object.defineProperty(window, 'location', {
      value: { ...window.location, assign: vi.fn(), href: '' },
      writable: true,
    })
  })

  it('shows the Download trigger button', () => {
    render(<DownloadMenu runId="run-1" />)
    expect(screen.getByRole('button', { name: /download/i })).toBeInTheDocument()
  })

  it('on CSV click, POSTs export then polls until ready and triggers download', async () => {
    ;(createExport as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      id: 'exp-1', run_id: 'run-1', format: 'csv',
      status: 'pending', size_bytes: null, error: null, download_url: null,
    })
    ;(getExport as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce({ id: 'exp-1', run_id: 'run-1', format: 'csv', status: 'pending', size_bytes: null, error: null, download_url: null })
      .mockResolvedValueOnce({ id: 'exp-1', run_id: 'run-1', format: 'csv', status: 'ready', size_bytes: 42, error: null, download_url: '/v3/exports/exp-1/download' })

    render(<DownloadMenu runId="run-1" pollIntervalMs={10} />)
    await userEvent.click(screen.getByRole('button', { name: /download/i }))
    await userEvent.click(await screen.findByText(/export as csv/i))

    await waitFor(() => expect(createExport).toHaveBeenCalledWith('run-1', 'csv'))
    await waitFor(() => expect(window.location.href).toContain('/v3/exports/exp-1/download'), { timeout: 1000 })
  })
})
