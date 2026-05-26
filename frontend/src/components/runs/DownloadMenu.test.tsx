import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { DownloadMenu } from './DownloadMenu'

vi.mock('@/api/v3', () => ({
  createExport: vi.fn(),
}))
vi.mock('@/api/client', () => ({
  api: { get: vi.fn() },
}))

import { createExport } from '@/api/v3'
import { api } from '@/api/client'

describe('DownloadMenu', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // jsdom lacks URL.createObjectURL
    Object.defineProperty(URL, 'createObjectURL', { value: vi.fn(() => 'blob:mock'), writable: true })
    Object.defineProperty(URL, 'revokeObjectURL', { value: vi.fn(), writable: true })
  })

  it('shows the Download trigger button', () => {
    render(<DownloadMenu runId="run-1" />)
    expect(screen.getByRole('button', { name: /download/i })).toBeInTheDocument()
  })

  it('on CSV click, creates the export then downloads the returned file as a blob', async () => {
    ;(createExport as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      filename: 'run-1.csv',
      url: '/v3/exports/files/run-1.csv',
    })
    ;(api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ data: new Blob(['a,b\n1,2']) })

    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})

    render(<DownloadMenu runId="run-1" />)
    await userEvent.click(screen.getByRole('button', { name: /download/i }))
    await userEvent.click(await screen.findByText(/export as csv/i))

    await waitFor(() => expect(createExport).toHaveBeenCalledWith('run-1', 'csv'))
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/v3/exports/files/run-1.csv', { responseType: 'blob' }))
    await waitFor(() => expect(clickSpy).toHaveBeenCalled())
    clickSpy.mockRestore()
  })

  it('surfaces an error if the export fails', async () => {
    ;(createExport as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new Error('export generation failed'))
    render(<DownloadMenu runId="run-1" />)
    await userEvent.click(screen.getByRole('button', { name: /download/i }))
    await userEvent.click(await screen.findByText(/export as csv/i))
    await waitFor(() => expect(screen.getByText(/export generation failed/i)).toBeInTheDocument())
  })
})
