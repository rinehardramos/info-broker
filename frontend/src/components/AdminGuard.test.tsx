import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'

// sessionStore mock — supports both selector and no-arg calls (AuthGuard uses
// both). We mutate `mockState` per test. userId is set truthy so AuthGuard's
// getMe hydration effect short-circuits (no async).
let mockState: { accessToken: string | null; isAdmin: boolean; userId: string | null; setUser: () => void }
vi.mock('../stores/sessionStore', () => ({
  useSessionStore: (selector?: (s: typeof mockState) => unknown) =>
    selector ? selector(mockState) : mockState,
}))

vi.mock('../api/v3', () => ({
  getMe: vi.fn(() => Promise.resolve({ id: 'u1', username: 'x', is_admin: false })),
}))

import AdminGuard from './AdminGuard'

function renderAt() {
  return render(
    <MemoryRouter initialEntries={['/admin/benchmarks']}>
      <Routes>
        <Route
          path="/admin/benchmarks"
          element={<AdminGuard><div>BENCHMARK PAGE</div></AdminGuard>}
        />
        <Route path="/dashboard" element={<div>DASHBOARD</div>} />
        <Route path="/login" element={<div>LOGIN</div>} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('AdminGuard', () => {
  beforeEach(() => {
    mockState = { accessToken: 'tok', isAdmin: false, userId: 'u1', setUser: () => {} }
  })

  it('renders the page for an admin', () => {
    mockState.isAdmin = true
    renderAt()
    expect(screen.getByText('BENCHMARK PAGE')).toBeInTheDocument()
  })

  it('redirects an authenticated non-admin to the dashboard', () => {
    mockState.isAdmin = false
    renderAt()
    expect(screen.queryByText('BENCHMARK PAGE')).not.toBeInTheDocument()
    expect(screen.getByText('DASHBOARD')).toBeInTheDocument()
  })

  it('redirects an unauthenticated visitor to login', () => {
    mockState.accessToken = null
    renderAt()
    expect(screen.queryByText('BENCHMARK PAGE')).not.toBeInTheDocument()
    expect(screen.getByText('LOGIN')).toBeInTheDocument()
  })
})
