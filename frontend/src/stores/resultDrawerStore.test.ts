import { describe, it, expect, beforeEach } from 'vitest'
import { useResultDrawerStore } from './resultDrawerStore'

describe('resultDrawerStore', () => {
  beforeEach(() => {
    useResultDrawerStore.setState({ isOpen: false, runId: null })
  })

  it('starts closed with no runId', () => {
    const s = useResultDrawerStore.getState()
    expect(s.isOpen).toBe(false)
    expect(s.runId).toBeNull()
  })

  it('open(runId) sets isOpen=true and stores runId', () => {
    useResultDrawerStore.getState().open('run-123')
    const s = useResultDrawerStore.getState()
    expect(s.isOpen).toBe(true)
    expect(s.runId).toBe('run-123')
  })

  it('close() clears the run and hides the drawer', () => {
    useResultDrawerStore.getState().open('run-123')
    useResultDrawerStore.getState().close()
    const s = useResultDrawerStore.getState()
    expect(s.isOpen).toBe(false)
    expect(s.runId).toBeNull()
  })
})
