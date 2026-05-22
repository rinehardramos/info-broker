import { queryClient } from './queryClient'
import { useChatStore } from '../stores/chatStore'
import { useModeStore } from '../stores/modeStore'

// localStorage keys that hold user-scoped data. On logout these MUST be wiped
// so the next user on the same browser cannot see the previous user's state.
// Device-scoped UI preferences (theme, column sizes) are intentionally excluded.
const USER_SCOPED_KEYS = [
  'access_token',
  'refresh_token',
  'ib-chat',
  'info-broker.mode',
  'locked_pipelines',
]

/**
 * Wipe all user-scoped client state. Safe to call from any context (React,
 * axios interceptor, storage event). Idempotent.
 */
export function clearClientSession(): void {
  queryClient.cancelQueries()
  queryClient.clear()

  // Reset persisted Zustand stores (clears in-memory state AND their storage keys).
  useChatStore.getState().clearMessages()
  useChatStore.persist.clearStorage()
  useModeStore.setState({ modeId: null })
  useModeStore.persist.clearStorage()

  for (const key of USER_SCOPED_KEYS) {
    try { localStorage.removeItem(key) } catch { /* storage may be unavailable */ }
  }
}

/**
 * Cross-tab logout: when another tab removes the access_token, this tab must
 * also wipe its state and bounce to /login. Without this, Tab B keeps showing
 * the prior user's cached data after Tab A logs out.
 */
export function installCrossTabLogoutListener(): () => void {
  const onStorage = (e: StorageEvent) => {
    if (e.key === 'access_token' && e.newValue === null) {
      clearClientSession()
      if (window.location.pathname !== '/login') {
        window.location.href = '/login'
      }
    }
  }
  window.addEventListener('storage', onStorage)
  return () => window.removeEventListener('storage', onStorage)
}
