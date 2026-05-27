// frontend/src/api/monitoring.ts
// Factory for the @platform/monitoring-ui typed API client.
// Bridges the existing infobroker auth/token model (localStorage access_token)
// to the monitoring-ui's injected `client` interface.

import { MonitoringClient } from '@platform/monitoring-ui'

const BASE = import.meta.env.VITE_API_URL || '/api'

/**
 * Returns a MonitoringClient configured with the infobroker API base URL
 * and the current session's access token. Call once per page mount.
 *
 * The `getToken` callback is called fresh on every request so token refreshes
 * (handled by the axios interceptor in client.ts) are reflected automatically.
 */
export function createAppMonitoringClient(): MonitoringClient {
  return new MonitoringClient({
    // baseUrl is the API ROOT only. MonitoringClient already prepends the full
    // "/v3/monitoring/..." path to every request, so adding it here would
    // double the prefix (→ /v3/monitoring/v3/monitoring/overview → 404).
    baseUrl: BASE,
    getToken: () => localStorage.getItem('access_token'),
  })
}
