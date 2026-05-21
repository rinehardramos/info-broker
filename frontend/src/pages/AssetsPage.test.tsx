import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

// Stub IconRail — it pulls in too many side-effect imports for a unit test.
vi.mock('@/components/layout/IconRail', () => ({ default: () => null }))

// Mock api client
const mockGet = vi.fn()
const mockPost = vi.fn()
const mockDelete = vi.fn()
vi.mock('@/api/client', () => ({
  api: {
    get:    (...a: unknown[]) => mockGet(...a),
    post:   (...a: unknown[]) => mockPost(...a),
    delete: (...a: unknown[]) => mockDelete(...a),
  },
}))

// Avoid debounce flake
vi.mock('@/hooks/useDebouncedLoading', () => ({ useDebouncedLoading: (v: boolean) => v }))

import AssetsPage from './AssetsPage'

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <AssetsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const ROW = {
  id: 'src-1',
  filename: 'sample.csv',
  file_type: 'csv',
  file_size_bytes: 2048,
  status: 'indexed',
  created_at: '2026-05-21T10:00:00Z',
  session_id: null,
  findings_count: 4,
}

describe('AssetsPage', () => {
  beforeEach(() => {
    mockGet.mockReset()
    mockPost.mockReset()
    mockDelete.mockReset()
  })

  it('renders empty state when no assets', async () => {
    mockGet.mockResolvedValueOnce({ data: [] })
    renderPage()
    await waitFor(() =>
      expect(screen.getByText(/No assets yet/i)).toBeInTheDocument(),
    )
  })

  it('renders a row for each asset', async () => {
    mockGet.mockResolvedValueOnce({ data: [ROW] })
    renderPage()
    await waitFor(() => expect(screen.getByText('sample.csv')).toBeInTheDocument())
    expect(screen.getByText(/2\.0 KB/i)).toBeInTheDocument()
    expect(screen.getByText(/indexed/i)).toBeInTheDocument()
  })

  it('filters rows by filename', async () => {
    mockGet.mockResolvedValueOnce({
      data: [ROW, { ...ROW, id: 'src-2', filename: 'other.pdf', file_type: 'pdf' }],
    })
    renderPage()
    await waitFor(() => expect(screen.getByText('sample.csv')).toBeInTheDocument())

    fireEvent.change(screen.getByPlaceholderText(/Filter by filename/i), {
      target: { value: 'other' },
    })
    expect(screen.queryByText('sample.csv')).not.toBeInTheDocument()
    expect(screen.getByText('other.pdf')).toBeInTheDocument()
  })

  it('calls DELETE when user confirms deletion', async () => {
    mockGet.mockResolvedValue({ data: [ROW] })
    mockDelete.mockResolvedValueOnce({ data: {} })
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)

    renderPage()
    await waitFor(() => expect(screen.getByText('sample.csv')).toBeInTheDocument())
    fireEvent.click(screen.getByTestId('delete-src-1'))

    await waitFor(() => expect(mockDelete).toHaveBeenCalledWith('/v3/sources/src-1'))
    confirmSpy.mockRestore()
  })

  it('does NOT delete when user cancels confirm', async () => {
    mockGet.mockResolvedValue({ data: [ROW] })
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false)

    renderPage()
    await waitFor(() => expect(screen.getByText('sample.csv')).toBeInTheDocument())
    fireEvent.click(screen.getByTestId('delete-src-1'))

    expect(mockDelete).not.toHaveBeenCalled()
    confirmSpy.mockRestore()
  })

  it('uploads via file input and refreshes the list', async () => {
    mockGet
      .mockResolvedValueOnce({ data: [] })           // initial empty
      .mockResolvedValueOnce({ data: [ROW] })        // after upload invalidation
    mockPost.mockResolvedValueOnce({ data: { source_id: 'src-1' } })

    renderPage()
    await waitFor(() => expect(screen.getByText(/No assets yet/i)).toBeInTheDocument())

    const input = screen.getByTestId('assets-file-input') as HTMLInputElement
    const file = new File(['col\n1\n'], 'sample.csv', { type: 'text/csv' })
    fireEvent.change(input, { target: { files: [file] } })

    await waitFor(() =>
      expect(mockPost).toHaveBeenCalledWith('/v3/sources/upload', expect.any(FormData)),
    )
  })

  it('handles { sources: [...] } response shape', async () => {
    mockGet.mockResolvedValueOnce({ data: { sources: [ROW] } })
    renderPage()
    await waitFor(() => expect(screen.getByText('sample.csv')).toBeInTheDocument())
  })
})
