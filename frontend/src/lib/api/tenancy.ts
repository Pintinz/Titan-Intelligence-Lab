import { api } from '@/lib/api/client'
import type { InvitationDto, MembershipDto, OrganizationDto, OrganizationRole, TeamDto } from '@/lib/api/types'

export const tenancyApi = {
  createOrganization: (name: string) => api.post<OrganizationDto>('/api/v1/organizations', { name }),
  createTeam: (organizationId: string, name: string) =>
    api.post<TeamDto>(`/api/v1/organizations/${organizationId}/teams`, { name }),
  listMembers: (organizationId: string) => api.get<MembershipDto[]>(`/api/v1/organizations/${organizationId}/members`),
  changeMemberRole: (organizationId: string, targetUserId: string, role: OrganizationRole) =>
    api.post<MembershipDto>(`/api/v1/organizations/${organizationId}/members/${targetUserId}/role`, { role }),
  removeMember: (organizationId: string, targetUserId: string) =>
    api.delete<{ removed: boolean }>(`/api/v1/organizations/${organizationId}/members/${targetUserId}`),
  inviteMember: (organizationId: string, email: string, role: OrganizationRole = 'member') =>
    api.post<InvitationDto & { raw_token: string }>(`/api/v1/organizations/${organizationId}/invitations`, {
      email,
      role,
    }),
  acceptInvitation: (token: string) =>
    api.post<MembershipDto>('/api/v1/organizations/invitations/accept', { token }),
  revokeInvitation: (organizationId: string, invitationId: string) =>
    api.delete<{ revoked: boolean }>(`/api/v1/organizations/${organizationId}/invitations/${invitationId}`),
}
