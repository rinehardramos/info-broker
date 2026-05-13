import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { StatusBadge } from './StatusBadge'

describe('StatusBadge', () => {
  it('renders the status label', () => {
    render(<StatusBadge status="succeeded" />)
    expect(screen.getByText(/succeeded/i)).toBeInTheDocument()
  })

  it('uses data-variant=success for succeeded', () => {
    render(<StatusBadge status="succeeded" />)
    expect(screen.getByText(/succeeded/i).closest('[data-variant]'))
      .toHaveAttribute('data-variant', 'success')
  })

  it('uses data-variant=danger for failed', () => {
    render(<StatusBadge status="failed" />)
    expect(screen.getByText(/failed/i).closest('[data-variant]'))
      .toHaveAttribute('data-variant', 'danger')
  })

  it('uses data-variant=running for running', () => {
    render(<StatusBadge status="running" />)
    expect(screen.getByText(/running/i).closest('[data-variant]'))
      .toHaveAttribute('data-variant', 'running')
  })
})
