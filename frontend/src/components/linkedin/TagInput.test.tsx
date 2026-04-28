import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import TagInput from './TagInput'

describe('TagInput', () => {
  it('renders existing tags', () => {
    render(<TagInput label="Job Titles" tags={['CEO', 'CTO']} onChange={vi.fn()} />)
    expect(screen.getByText('CEO')).toBeInTheDocument()
    expect(screen.getByText('CTO')).toBeInTheDocument()
  })

  it('adds a tag on Enter', async () => {
    const onChange = vi.fn()
    render(<TagInput label="Job Titles" tags={[]} onChange={onChange} />)
    const input = screen.getByRole('textbox')
    await userEvent.type(input, 'CEO{Enter}')
    expect(onChange).toHaveBeenCalledWith(['CEO'])
  })

  it('adds a tag on comma', async () => {
    const onChange = vi.fn()
    render(<TagInput label="Job Titles" tags={[]} onChange={onChange} />)
    const input = screen.getByRole('textbox')
    await userEvent.type(input, 'CEO,')
    expect(onChange).toHaveBeenCalledWith(['CEO'])
  })

  it('removes a tag when × is clicked', async () => {
    const onChange = vi.fn()
    render(<TagInput label="Job Titles" tags={['CEO', 'CTO']} onChange={onChange} />)
    await userEvent.click(screen.getByLabelText('Remove CEO'))
    expect(onChange).toHaveBeenCalledWith(['CTO'])
  })

  it('removes last tag on Backspace when input is empty', async () => {
    const onChange = vi.fn()
    render(<TagInput label="Job Titles" tags={['CEO', 'CTO']} onChange={onChange} />)
    const input = screen.getByRole('textbox')
    fireEvent.keyDown(input, { key: 'Backspace' })
    expect(onChange).toHaveBeenCalledWith(['CEO'])
  })

  it('does not add duplicate tags', async () => {
    const onChange = vi.fn()
    render(<TagInput label="Job Titles" tags={['CEO']} onChange={onChange} />)
    const input = screen.getByRole('textbox')
    await userEvent.type(input, 'CEO{Enter}')
    expect(onChange).not.toHaveBeenCalled()
  })

  it('adds tag on blur', async () => {
    const onChange = vi.fn()
    render(<TagInput label="Job Titles" tags={[]} onChange={onChange} />)
    const input = screen.getByRole('textbox')
    await userEvent.type(input, 'CTO')
    fireEvent.blur(input)
    expect(onChange).toHaveBeenCalledWith(['CTO'])
  })
})
