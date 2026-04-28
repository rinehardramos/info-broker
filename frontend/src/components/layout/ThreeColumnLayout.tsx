import { PanelGroup, Panel, PanelResizeHandle } from 'react-resizable-panels'
import { useLayoutStore } from '../../stores/layoutStore'
import { updatePreferences } from '../../api/v3'
import { useSessionStore } from '../../stores/sessionStore'

interface Props {
  col1: React.ReactNode
  col2: React.ReactNode
  col3: React.ReactNode
}

export default function ThreeColumnLayout({ col1, col2, col3 }: Props) {
  const { sizes, setSizes } = useLayoutStore()
  const token               = useSessionStore(s => s.accessToken)

  function handleResize(newSizes: number[]) {
    const next = { col1: newSizes[0], col2: newSizes[1], col3: newSizes[2] }
    setSizes(next)
    if (token) {
      updatePreferences({ column_layout: next }).catch(() => {/* ignore */})
    }
  }

  return (
    <PanelGroup
      direction="horizontal"
      onLayout={handleResize}
      style={{ height: '100%', flex: 1, overflow: 'hidden' }}
    >
      <Panel defaultSize={sizes.col1} minSize={20}>
        <div className="col-scroll h-full" style={{ background: 'var(--bg)' }}>
          {col1}
        </div>
      </Panel>

      <PanelResizeHandle
        style={{ width: 3, background: 'var(--border)', cursor: 'col-resize' }}
      />

      <Panel defaultSize={sizes.col2} minSize={15}>
        <div className="col-scroll h-full" style={{ background: 'var(--panel)' }}>
          {col2}
        </div>
      </Panel>

      <PanelResizeHandle
        style={{ width: 3, background: 'var(--border)', cursor: 'col-resize' }}
      />

      <Panel defaultSize={sizes.col3} minSize={10}>
        <div className="col-scroll h-full" style={{ background: 'var(--panel)' }}>
          {col3}
        </div>
      </Panel>
    </PanelGroup>
  )
}
