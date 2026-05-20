import { api } from './client'

export interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
}

export interface MeResponse {
  id: string
  username: string
  email: string | null
  is_active: boolean
  is_admin: boolean
  created_at: string
  password_set: boolean
  oauth_provider: string | null
  avatar_url: string | null
  display_name: string | null
  timezone: string | null
  locale: string | null
}

export interface ProfileUpdate {
  display_name?: string | null
  avatar_url?:   string | null
  timezone?:     string | null
  locale?:       string | null
}

export async function login(username: string, password: string): Promise<TokenResponse> {
  const { data } = await api.post<TokenResponse>('/v3/auth/login', { username, password })
  return data
}

export async function getMe(): Promise<MeResponse> {
  const { data } = await api.get<MeResponse>('/v3/users/me')
  return data
}

export async function updateProfile(body: ProfileUpdate): Promise<MeResponse> {
  const { data } = await api.patch<MeResponse>('/v3/users/me', body)
  return data
}

export async function changePassword(current_password: string, new_password: string): Promise<void> {
  await api.post('/v3/auth/change-password', { current_password, new_password })
}

export async function setPassword(new_password: string): Promise<void> {
  await api.post('/v3/auth/set-password', { new_password })
}
