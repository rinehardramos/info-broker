import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { RunBadge } from './RunBadge'

describe('RunBadge', () => {
  it('renders the first 8 chars of the run_id', () => {
    render(<RunBadge runId="3dc3fc50-745a-45e7-9002-f915da9bd5d8" />)
    expect(screen.getByTestId('run-badge')).toHaveTextContent('3dc3fc50')
  })

  it('exposes the full UUID via the title attribute', () => {
    render(<RunBadge runId="3dc3fc50-745a-45e7-9002-f915da9bd5d8" />)
    const el = screen.getByTestId('run-badge')
    expect(el).toHaveAttribute('title', '3dc3fc50-745a-45e7-9002-f915da9bd5d8')
  })

  it('copies the full UUID on click', async () => {
    const writeText = vi.fn(async () => {})
    Object.assign(navigator, { clipboard: { writeText } })
    render(<RunBadge runId="3dc3fc50-745a-45e7-9002-f915da9bd5d8" />)
    fireEvent.click(screen.getByTestId('run-badge'))
    expect(writeText).toHaveBeenCalledWith('3dc3fc50-745a-45e7-9002-f915da9bd5d8')
  })

  it('handles missing or short ids gracefully', () => {
    render(<RunBadge runId="" />)
    expect(screen.getByTestId('run-badge')).toHaveTextContent('-')
  })
})
