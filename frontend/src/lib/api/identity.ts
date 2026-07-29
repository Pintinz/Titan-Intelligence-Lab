import { api } from '@/lib/api/client'
import type { PersonalAccessTokenDto, Role, SessionDto, UserDto } from '@/lib/api/types'

export const identityApi = {
  me: () => api.get<UserDto>('/api/v1/users/me'),
  changeRole: (userId: string, role: Role) => api.post<UserDto>(`/api/v1/users/${userId}/role`, { role }),
  mySessions: () => api.get<SessionDto[]>('/api/v1/users/me/sessions'),
  revokeSession: (sessionId: string) => api.delete<{ revoked: boolean }>(`/api/v1/users/me/sessions/${sessionId}`),
  myTokens: () => api.get<PersonalAccessTokenDto[]>('/api/v1/users/me/tokens'),
  createToken: (name: string, scopes: string[]) =>
    api.post<{ id: string; name: string; scopes: string[]; raw_token: string }>('/api/v1/users/me/tokens', {
      name,
      scopes,
    }),
  revokeToken: (tokenId: string) => api.delete<{ revoked: boolean }>(`/api/v1/users/me/tokens/${tokenId}`),
}
