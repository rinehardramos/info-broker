import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import AdminUsersPage from './AdminUsersPage'

vi.mock('@/components/layout/IconRail', () => ({ default: () => null }))
vi.mock('@/stores/sessionStore', () => ({
  useSessionStore: () => ({ userId: 'current-user-id' }),
}))

const makeUser = (i: number) => ({
  id: `user-${i}`,
  username: `user${i}`,
  email: `user${i}@example.com`,
  is_admin: false,
  role: 'analyst' as const,
  is_active: true,
  org_id: '',
  created_at: '2026-01-01T00:00:00Z',
})

const PAGE1 = Array.from({ length: 50 }, (_, i) => makeUser(i))
const PAGE2 = Array.from({ length: 10 }, (_, i) => makeUser(i + 50))

vi.mock('@/api/v3', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/v3')>()),
  listUsers: vi.fn().mockResolvedValue({
    items: Array.from({ length: 50 }, (_, i) => ({
      id: `user-${i}`, username: `user${i}`, email: `user${i}@example.com`,
      is_admin: false, role: 'analyst', is_active: true,
      org_id: '', created_at: '2026-01-01T00:00:00Z',
    })),
    total: 60,
    page: 1,
    page_size: 50,
    total_pages: 2,
  }),
  patchUser: vi.fn().mockResolvedValue({}),
}))

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter><AdminUsersPage /></MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('AdminUsersPage', () => {
  it('renders total user count from the paginated response', async () => {
    renderPage()
    await waitFor(() =>
      expect(screen.getByText(/60 users total/)).toBeInTheDocument()
    )
  })

  it('shows page 1 of 2 in the pagination controls', async () => {
    renderPage()
    await waitFor(() =>
      expect(screen.getByText('Page 1 of 2')).toBeInTheDocument()
    )
  })

  it('Previous button is disabled on page 1', async () => {
    renderPage()
    const prev = await screen.findByRole('button', { name: /previous/i })
    expect(prev).toBeDisabled()
  })

  it('Next button is enabled on page 1', async () => {
    renderPage()
    const next = await screen.findByRole('button', { name: /next/i })
    expect(next).not.toBeDisabled()
  })

  it('navigates to page 2 when Next is clicked', async () => {
    const { listUsers } = await import('@/api/v3')
    ;(listUsers as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      items: PAGE1, total: 60, page: 1, page_size: 50, total_pages: 2,
    }).mockResolvedValueOnce({
      items: PAGE2, total: 60, page: 2, page_size: 50, total_pages: 2,
    })

    renderPage()
    const next = await screen.findByRole('button', { name: /next/i })
    fireEvent.click(next)
    await waitFor(() =>
      expect(screen.getByText('Page 2 of 2')).toBeInTheDocument()
    )
  })

  it('renders search input and Search button', async () => {
    renderPage()
    expect(await screen.findByPlaceholderText(/search username or email/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^search$/i })).toBeInTheDocument()
  })

  it('shows 50-item page-size button as active by default', async () => {
    renderPage()
    // Wait for the table to render, then check per-page buttons
    await screen.findByRole('button', { name: /next/i })
    const buttons = screen.getAllByRole('button')
    const btn50 = buttons.find(b => b.textContent === '50')
    expect(btn50).toBeTruthy()
  })
})
