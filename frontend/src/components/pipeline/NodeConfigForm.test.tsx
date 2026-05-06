import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { NodeConfigForm } from './NodeConfigForm'

const NODES = [
  { id: 'n1', node_type: 'agent_input', label: 'Agent Input', config: {}, category: 'source' },
  { id: 'n2', node_type: 'ddg_search',  label: 'DDG Search',  config: {}, category: 'enrich' },
  { id: 'n3', node_type: 'ai_scoring',  label: 'AI Scoring',  config: {}, category: 'score'  },
]

function renderForm(activeNodeIdx: number) {
  return render(
    <NodeConfigForm
      node={NODES[activeNodeIdx]}
      schema={{}}
      onChange={vi.fn()}
      onClose={vi.fn()}
      nodes={NODES}
      edges={[]}
      onEdgeChange={vi.fn()}
    />,
  )
}

describe('NodeConfigForm — OUTPUTS panel', () => {
  it('does not show source nodes as output targets', () => {
    renderForm(1) // open ddg_search config
    expect(screen.getByText('OUTPUTS')).toBeInTheDocument()
    // Non-source nodes appear
    expect(screen.getByTestId('output-connect-ai_scoring')).toBeInTheDocument()
    // Source node must NOT appear
    expect(screen.queryByTestId('output-connect-agent_input')).not.toBeInTheDocument()
  })

  it('does not show source nodes as output targets when current node is a score node', () => {
    renderForm(2) // open ai_scoring config
    // ddg_search (enrich) can appear
    expect(screen.getByTestId('output-connect-ddg_search')).toBeInTheDocument()
    // agent_input (source) must NOT appear
    expect(screen.queryByTestId('output-connect-agent_input')).not.toBeInTheDocument()
  })

  it('source node itself shows non-source nodes as output targets', () => {
    renderForm(0) // open agent_input config — it is a source, but can connect TO enrich/score
    expect(screen.getByTestId('output-connect-ddg_search')).toBeInTheDocument()
    expect(screen.getByTestId('output-connect-ai_scoring')).toBeInTheDocument()
  })
})
