import axios from 'axios'
import { clearClientSession } from '../lib/clearClientSession'

// Same-origin /api is proxied by Vite in dev. Production builds on Cloudflare
// Pages set VITE_API_URL=https://api.infobroker.tech so requests cross the
// tunnel directly. Override via env at build time.
const BASE = import.meta.env.VITE_API_URL || "/api"

export const api = axios.create({ baseURL: BASE })

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  (r) => r,
  async (err) => {
    const original = err.config
    if (err.response?.status === 401 && !original._retry) {
      // Don't intercept the login endpoint itself — let Login.tsx handle the error
      if (original.url?.includes('/v3/auth/login')) return Promise.reject(err)
      original._retry = true
      const refresh = localStorage.getItem('refresh_token')
      if (refresh) {
        try {
          const { data } = await axios.post(`${BASE}/v3/auth/refresh`, { refresh_token: refresh })
          localStorage.setItem('access_token', data.access_token)
          localStorage.setItem('refresh_token', data.refresh_token)
          original.headers.Authorization = `Bearer ${data.access_token}`
          return api(original)
        } catch {
          // refresh failed — fall through to redirect
        }
      }
      clearClientSession()
      window.location.href = '/login'
    }
    return Promise.reject(err)
  },
)
