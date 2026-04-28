import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { FormProvider, useForm } from 'react-hook-form'
import SchemaFormRenderer from './SchemaFormRenderer'

function Wrapper({ schema }: { schema: Record<string, unknown> }) {
  const methods = useForm()
  return (
    <FormProvider {...methods}>
      <SchemaFormRenderer schema={schema} />
    </FormProvider>
  )
}

describe('SchemaFormRenderer', () => {
  it('renders string field from schema', () => {
    render(<Wrapper schema={{
      type: 'object',
      properties: {
        actor_id: { type: 'string', title: 'Actor ID', default: 'apify/linkedin' },
      },
    }} />)
    expect(screen.getByLabelText('Actor ID')).toBeInTheDocument()
  })

  it('renders integer field with min/max', () => {
    render(<Wrapper schema={{
      type: 'object',
      properties: {
        max_results: { type: 'integer', title: 'Max Results', default: 25, minimum: 1, maximum: 200 },
      },
    }} />)
    const input = screen.getByLabelText('Max Results')
    expect(input).toHaveAttribute('type', 'number')
    expect(input).toHaveAttribute('min', '1')
    expect(input).toHaveAttribute('max', '200')
  })
})
