// frontend/src/pages/MonitoringPage.tsx
// Admin-only monitoring dashboard — renders the @platform/monitoring-ui
// MonitoringDashboard (Overview, Traffic & Geo, API & MCP tabs).
// Alerts & Enforcement tab is Phase 2; the component renders it
// in read-only / placeholder mode until Phase 2 ships.

import { useMemo } from 'react'
import { MonitoringDashboard } from '@platform/monitoring-ui'
import '@platform/monitoring-ui/theme.css'
import IconRail from '../components/layout/IconRail'
import { createAppMonitoringClient } from '../api/monitoring'

export default function MonitoringPage() {
  // createAppMonitoringClient() is cheap (no network call); memo so the client
  // instance is stable across re-renders (prevents hook re-subscription in useLiveFeed).
  const client = useMemo(() => createAppMonitoringClient(), [])

  return (
    <div style={{ display: 'flex', height: '100vh', overflow: 'hidden' }}>
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0, overflow: 'auto' }}>
        <MonitoringDashboard client={client} />
      </div>
      <IconRail />
    </div>
  )
}
