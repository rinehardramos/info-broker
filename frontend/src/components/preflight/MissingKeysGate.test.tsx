import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

vi.mock('../../api/v3', () => ({
  storeApiKey: vi.fn().mockResolvedValue(undefined),
}))

import MissingKeysGate from './MissingKeysGate'
import type { MissingKeyTool } from '../../hooks/usePreflight'

const TOOLS: MissingKeyTool[] = [
  {
    technique_id: 'hunter_email_search',
    key_name: 'hunter_io_api_key',
    display_name: 'Hunter.io (email finder)',
    setup_url: 'https://hunter.io/api-keys',
    setup_instructions: 'Create a free Hunter.io account and copy the API key.',
  },
  {
    technique_id: 'apollo_contact',
    key_name: 'apollo_api_key',
    display_name: 'Apollo.io (contact enrichment)',
    setup_url: 'https://developer.apollo.io/keys/',
    setup_instructions: 'Generate an API key in Apollo settings.',
  },
]

describe('MissingKeysGate', () => {
  it('renders a card per missing tool with setup info', () => {
    render(<MissingKeysGate missingTools={TOOLS} onKeyStored={vi.fn()} onProceedAnyway={vi.fn()} />)
    expect(screen.getByTestId('missing-key-card-hunter_io_api_key')).toBeInTheDocument()
    expect(screen.getByTestId('missing-key-card-apollo_api_key')).toBeInTheDocument()
    expect(screen.getByText(/Hunter.io \(email finder\)/)).toBeInTheDocument()
    // setup link points at the real URL
    expect(screen.getByTestId('missing-key-setup-url-hunter_io_api_key')).toHaveAttribute(
      'href', 'https://hunter.io/api-keys',
    )
  })

  it('"Proceed anyway" invokes the callback', () => {
    const onProceed = vi.fn()
    render(<MissingKeysGate missingTools={TOOLS} onKeyStored={vi.fn()} onProceedAnyway={onProceed} />)
    fireEvent.click(screen.getByTestId('missing-keys-proceed-anyway'))
    expect(onProceed).toHaveBeenCalledTimes(1)
  })

  it('entering a key stores it (user scope) and notifies the parent', async () => {
    const { storeApiKey } = await import('../../api/v3')
    const onKeyStored = vi.fn()
    render(<MissingKeysGate missingTools={TOOLS} onKeyStored={onKeyStored} onProceedAnyway={vi.fn()} />)

    fireEvent.change(screen.getByTestId('missing-key-input-hunter_io_api_key'), {
      target: { value: 'secret-key-123' },
    })
    fireEvent.click(screen.getByTestId('missing-key-save-hunter_io_api_key'))

    await waitFor(() => expect(storeApiKey).toHaveBeenCalledWith('hunter_io_api_key', 'secret-key-123', 'user'))
    await waitFor(() => expect(onKeyStored).toHaveBeenCalled())
    // card flips to a saved confirmation
    await waitFor(() => expect(screen.getByTestId('missing-key-saved-hunter_io_api_key')).toBeInTheDocument())
  })

  it('Save is disabled until a value is entered', () => {
    render(<MissingKeysGate missingTools={TOOLS} onKeyStored={vi.fn()} onProceedAnyway={vi.fn()} />)
    expect(screen.getByTestId('missing-key-save-hunter_io_api_key')).toBeDisabled()
  })
})
