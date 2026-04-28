import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

vi.mock('../api/auth', () => ({
  login: vi.fn().mockResolvedValue({
    access_token: 'test-access',
    refresh_token: 'test-refresh',
    token_type: 'bearer',
  }),
}))

import Login from './Login'

function renderLogin() {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <Login />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('Login', () => {
  it('renders username and password fields', () => {
    renderLogin()
    expect(screen.getByPlaceholderText('username')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('password')).toBeInTheDocument()
  })

  it('calls login on submit', async () => {
    const { login } = await import('../api/auth')
    renderLogin()
    fireEvent.change(screen.getByPlaceholderText('username'), { target: { value: 'admin' } })
    fireEvent.change(screen.getByPlaceholderText('password'), { target: { value: 'secret' } })
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }))
    await waitFor(() => expect(login).toHaveBeenCalledWith('admin', 'secret'))
  })
})
