import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { AdminGateDetail } from './AdminGateDetail'
import type { GateResult } from '@/types/gate'

const failingGate: GateResult = {
  passed: false,
  failing_check_kind: 'no_brain_work',
  failing_check_detail: { tool_calls: 0, findings: 0 },
  brain_summary: {
    tool_calls: 0, findings: 0, hypothesis_count: 0,
    duration_ms: 73, invoked_tools: [],
  },
}

describe('AdminGateDetail', () => {
  it('renders failing_check_kind prominently', () => {
    render(<AdminGateDetail detail={failingGate} />)
    expect(screen.getByText(/no_brain_work/)).toBeInTheDocument()
  })

  it('renders brain summary counts', () => {
    render(<AdminGateDetail detail={failingGate} />)
    expect(screen.getByText(/tool calls/i)).toBeInTheDocument()
    expect(screen.getByText(/findings/i)).toBeInTheDocument()
    expect(screen.getByText(/73\s*ms/)).toBeInTheDocument()
  })

  it('shows null state for missing detail', () => {
    render(<AdminGateDetail detail={null} />)
    expect(screen.getByText(/no gate data/i)).toBeInTheDocument()
  })

  it('renders invoked tools when present', () => {
    const gateWithTools: GateResult = {
      ...failingGate,
      brain_summary: { ...failingGate.brain_summary, invoked_tools: ['run_web_search', 'run_whois_lookup'] },
    }
    render(<AdminGateDetail detail={gateWithTools} />)
    expect(screen.getByText(/run_web_search/)).toBeInTheDocument()
    expect(screen.getByText(/run_whois_lookup/)).toBeInTheDocument()
  })

  it('renders failing_check_detail JSON when non-empty', () => {
    render(<AdminGateDetail detail={failingGate} />)
    // JSON pretty-printed should include the keys from failing_check_detail
    expect(screen.getByText(/"tool_calls": 0/)).toBeInTheDocument()
  })
})
