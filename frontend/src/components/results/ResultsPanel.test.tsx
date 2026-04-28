import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

import ResultsPanel from './ResultsPanel'

describe('ResultsPanel', () => {
  it('renders tab bar with Profiles, News, Social, Summary tabs', () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter><ResultsPanel /></MemoryRouter>
      </QueryClientProvider>,
    )
    expect(screen.getByText('Profiles')).toBeInTheDocument()
    expect(screen.getByText('News')).toBeInTheDocument()
    expect(screen.getByText('Social')).toBeInTheDocument()
    expect(screen.getByText('Summary')).toBeInTheDocument()
  })
})
