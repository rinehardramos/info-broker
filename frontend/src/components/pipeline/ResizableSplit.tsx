import { PanelGroup, Panel, PanelResizeHandle } from 'react-resizable-panels'
import { ReactNode } from 'react'

interface Props {
  left: ReactNode
  right: ReactNode
}

export function ResizableSplit({ left, right }: Props) {
  return (
    <PanelGroup direction="horizontal" style={{ height: '100%' }}>
      <Panel defaultSize={40} minSize={20} maxSize={60}>
        <div style={{ height: '100%', overflow: 'auto' }}>{left}</div>
      </Panel>
      <PanelResizeHandle
        style={{
          width: 4,
          background: 'var(--border)',
          cursor: 'col-resize',
          flexShrink: 0,
        }}
      />
      <Panel minSize={30}>
        <div style={{ height: '100%', overflow: 'auto' }}>{right}</div>
      </Panel>
    </PanelGroup>
  )
}
