import { api } from './client'

export interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
}

export async function login(username: string, password: string): Promise<TokenResponse> {
  const { data } = await api.post<TokenResponse>('/v3/auth/login', { username, password })
  return data
}
