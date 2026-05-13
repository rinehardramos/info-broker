import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { RunListTable } from './RunListTable'
import type { RunRow } from '@/api/v3'

const rows: RunRow[] = [
  {
    id: 'r1', status: 'succeeded', query: 'investigate: ACME',
    pipeline_name: null, trigger_type: 'investigation',
    created_at: '2026-05-13T10:00:00Z', finished_at: '2026-05-13T10:00:45Z',
  },
  {
    id: 'r2', status: 'running', query: 'pipeline: media-id',
    pipeline_name: 'media-id', trigger_type: 'pipeline',
    created_at: '2026-05-13T10:05:00Z', finished_at: null,
  },
]

describe('RunListTable', () => {
  it('renders one row per run with query and duration', () => {
    render(<RunListTable rows={rows} onShow={() => {}} />)
    expect(screen.getByText(/investigate: ACME/)).toBeInTheDocument()
    expect(screen.getByText(/pipeline: media-id/)).toBeInTheDocument()
    expect(screen.getByText('45s')).toBeInTheDocument()
    expect(screen.getByText('—')).toBeInTheDocument()
  })

  it('renders Show on every row and Download only on completed runs', () => {
    render(<RunListTable rows={rows} onShow={() => {}} />)
    expect(screen.getAllByRole('button', { name: /show/i })).toHaveLength(2)
    expect(screen.getAllByRole('button', { name: /download/i })).toHaveLength(1)
  })

  it('calls onShow(runId) when Show is clicked', async () => {
    const onShow = vi.fn()
    render(<RunListTable rows={rows} onShow={onShow} />)
    await userEvent.click(screen.getAllByRole('button', { name: /show/i })[0])
    expect(onShow).toHaveBeenCalledWith('r1')
  })

  it('renders empty state when no rows', () => {
    render(<RunListTable rows={[]} onShow={() => {}} />)
    expect(screen.getByText(/no runs yet/i)).toBeInTheDocument()
  })
})
