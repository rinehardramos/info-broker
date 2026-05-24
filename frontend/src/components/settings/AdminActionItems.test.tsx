import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

// ---------------------------------------------------------------------------
// Mocks — declared before importing component under test
// ---------------------------------------------------------------------------

const mockGetNodeHealth = vi.fn()

vi.mock('../../api/v3', () => ({
  getNodeHealth: () => mockGetNodeHealth(),
}))

// sessionStore mock — we control isAdmin per test via `mockIsAdmin`
let mockIsAdmin = true

vi.mock('../../stores/sessionStore', () => ({
  useSessionStore: (selector: (s: { isAdmin: boolean }) => unknown) =>
    selector({ isAdmin: mockIsAdmin }),
}))

import AdminActionItems from './AdminActionItems'

// ---------------------------------------------------------------------------
// Fixture data
// ---------------------------------------------------------------------------

const UNHEALTHY_NODE = {
  node_type: 'apify_zillow',
  display_name: 'Apify Zillow',
  healthy: false,
  error: 'Missing API key',
  requires_key: 'APIFY_API_TOKEN',
  setup_url: 'https://apify.com/signup',
  setup_instructions: 'Sign up at Apify and copy your token from Account > Integrations.',
}

const HEALTHY_NODE = {
  node_type: 'google_search',
  display_name: 'Google Search',
  healthy: true,
  error: null,
  requires_key: null,
  setup_url: null,
  setup_instructions: null,
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function wrap(ui: React.ReactNode) {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  )
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

beforeEach(() => {
  vi.clearAllMocks()
  mockIsAdmin = true
})

describe('AdminActionItems', () => {
  it('shows the unhealthy node as an action item', async () => {
    mockGetNodeHealth.mockResolvedValue([UNHEALTHY_NODE, HEALTHY_NODE])

    wrap(<AdminActionItems onNavigateToCoreSettings={vi.fn()} />)

    await waitFor(() =>
      expect(screen.getByTestId('admin-action-items')).toBeInTheDocument(),
    )

    // Action item for the unhealthy node should appear
    expect(screen.getByTestId('action-item-apify_zillow')).toBeInTheDocument()
    expect(screen.getByText('Apify Zillow')).toBeInTheDocument()
  })

  it('shows requires_key on the action item', async () => {
    mockGetNodeHealth.mockResolvedValue([UNHEALTHY_NODE, HEALTHY_NODE])

    wrap(<AdminActionItems onNavigateToCoreSettings={vi.fn()} />)

    await waitFor(() =>
      expect(screen.getByTestId('action-item-requires-key-apify_zillow')).toBeInTheDocument(),
    )

    expect(screen.getByTestId('action-item-requires-key-apify_zillow').textContent).toContain(
      'APIFY_API_TOKEN',
    )
  })

  it('shows the setup_url link for the unhealthy node', async () => {
    mockGetNodeHealth.mockResolvedValue([UNHEALTHY_NODE, HEALTHY_NODE])

    wrap(<AdminActionItems onNavigateToCoreSettings={vi.fn()} />)

    await waitFor(() =>
      expect(screen.getByTestId('action-item-setup-url-apify_zillow')).toBeInTheDocument(),
    )

    const link = screen.getByTestId('action-item-setup-url-apify_zillow') as HTMLAnchorElement
    expect(link.href).toBe('https://apify.com/signup')
    expect(link.target).toBe('_blank')
  })

  it('does NOT show the healthy node as an action item', async () => {
    mockGetNodeHealth.mockResolvedValue([UNHEALTHY_NODE, HEALTHY_NODE])

    wrap(<AdminActionItems onNavigateToCoreSettings={vi.fn()} />)

    await waitFor(() =>
      expect(screen.getByTestId('admin-action-items')).toBeInTheDocument(),
    )

    expect(screen.queryByTestId('action-item-google_search')).not.toBeInTheDocument()
  })

  it('shows "All tools healthy" empty state when no action items', async () => {
    mockGetNodeHealth.mockResolvedValue([HEALTHY_NODE])

    wrap(<AdminActionItems onNavigateToCoreSettings={vi.fn()} />)

    await waitFor(() =>
      expect(screen.getByTestId('all-healthy-state')).toBeInTheDocument(),
    )

    expect(screen.getByText(/All tools healthy/)).toBeInTheDocument()
  })

  it('shows action-items badge count when items exist', async () => {
    mockGetNodeHealth.mockResolvedValue([UNHEALTHY_NODE, HEALTHY_NODE])

    wrap(<AdminActionItems onNavigateToCoreSettings={vi.fn()} />)

    await waitFor(() =>
      expect(screen.getByTestId('action-items-badge')).toBeInTheDocument(),
    )

    expect(screen.getByTestId('action-items-badge').textContent).toBe('1')
  })

  it('renders nothing for non-admin users', () => {
    mockIsAdmin = false
    mockGetNodeHealth.mockResolvedValue([UNHEALTHY_NODE])

    const { container } = wrap(<AdminActionItems onNavigateToCoreSettings={vi.fn()} />)

    // Component returns null for non-admin
    expect(container.firstChild).toBeNull()
  })

  it('calls onNavigateToCoreSettings when Configure button is clicked', async () => {
    mockGetNodeHealth.mockResolvedValue([UNHEALTHY_NODE])
    const onNavigate = vi.fn()

    wrap(<AdminActionItems onNavigateToCoreSettings={onNavigate} />)

    await waitFor(() =>
      expect(screen.getByTestId('action-item-configure-apify_zillow')).toBeInTheDocument(),
    )

    screen.getByTestId('action-item-configure-apify_zillow').click()
    expect(onNavigate).toHaveBeenCalledTimes(1)
  })
})
