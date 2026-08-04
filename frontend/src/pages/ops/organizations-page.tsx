import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Building2, UserPlus, Trash2, Send } from 'lucide-react'
import { tenancyApi } from '@/lib/api/tenancy'
import type { OrganizationDto, OrganizationRole } from '@/lib/api/types'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { ErrorState } from '@/components/ui/error-state'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { OpsPageHeader, SectionCard, BackendPendingState } from '@/components/ops/ops-primitives'
import { toast } from '@/stores/toast-store'

function OrganizationMembers({ organization }: { organization: OrganizationDto }) {
  const [inviteEmail, setInviteEmail] = useState('')
  const [inviteRole, setInviteRole] = useState<OrganizationRole>('member')
  const queryClient = useQueryClient()

  const membersQuery = useQuery({
    queryKey: ['tenancy', 'members', organization.id],
    queryFn: () => tenancyApi.listMembers(organization.id),
  })

  const invite = useMutation({
    mutationFn: () => tenancyApi.inviteMember(organization.id, inviteEmail, inviteRole),
    onSuccess: () => {
      toast.success('Invitation sent', inviteEmail)
      setInviteEmail('')
      void queryClient.invalidateQueries({ queryKey: ['tenancy', 'members', organization.id] })
    },
    onError: (error) => toast.danger('Could not send invitation', error instanceof Error ? error.message : undefined),
  })

  const changeRole = useMutation({
    mutationFn: ({ userId, role }: { userId: string; role: OrganizationRole }) => tenancyApi.changeMemberRole(organization.id, userId, role),
    onSuccess: () => void membersQuery.refetch(),
  })

  const remove = useMutation({
    mutationFn: (userId: string) => tenancyApi.removeMember(organization.id, userId),
    onSuccess: () => void membersQuery.refetch(),
  })

  return (
    <SectionCard icon={Building2} title={organization.name} description={`Organization ID: ${organization.id}`}>
      <div className="mb-4 flex flex-wrap items-end gap-2 border-b border-border-subtle pb-4">
        <div>
          <Label htmlFor="invite-email">Invite by email</Label>
          <Input id="invite-email" type="email" value={inviteEmail} onChange={(e) => setInviteEmail(e.target.value)} className="mt-1.5 w-56" />
        </div>
        <Select value={inviteRole} onValueChange={(v) => setInviteRole(v as OrganizationRole)}>
          <SelectTrigger className="w-32"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="member">Member</SelectItem>
            <SelectItem value="admin">Admin</SelectItem>
            <SelectItem value="owner">Owner</SelectItem>
          </SelectContent>
        </Select>
        <Button size="sm" onClick={() => invite.mutate()} disabled={!inviteEmail || invite.isPending} className="gap-1">
          <Send className="size-3.5" /> {invite.isPending ? 'Sending…' : 'Invite'}
        </Button>
      </div>

      {membersQuery.isPending && <Skeleton className="h-20" />}
      {membersQuery.isError && <ErrorState error={membersQuery.error} onRetry={() => void membersQuery.refetch()} />}
      {membersQuery.data && membersQuery.data.length === 0 && <p className="text-sm text-text-secondary">No members yet.</p>}
      {membersQuery.data && membersQuery.data.length > 0 && (
        <ul className="space-y-1.5">
          {membersQuery.data.map((m) => (
            <li key={m.user_id} className="flex items-center justify-between gap-3 rounded-md border border-border-default p-2.5">
              <div className="min-w-0">
                <p className="truncate font-mono text-xs text-text-primary">{m.user_id}</p>
                <p className="text-[11px] text-text-muted">Joined {new Date(m.joined_at).toLocaleDateString()}</p>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <Select value={m.role} onValueChange={(v) => changeRole.mutate({ userId: m.user_id, role: v as OrganizationRole })}>
                  <SelectTrigger className="h-8 w-28 text-xs"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="member">Member</SelectItem>
                    <SelectItem value="admin">Admin</SelectItem>
                    <SelectItem value="owner">Owner</SelectItem>
                  </SelectContent>
                </Select>
                <Button size="icon" variant="ghost" onClick={() => remove.mutate(m.user_id)} disabled={remove.isPending} aria-label="Remove member">
                  <Trash2 className="size-3.5 text-danger" />
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </SectionCard>
  )
}

export default function OrganizationsPage() {
  const [orgName, setOrgName] = useState('')
  const [managedOrgId, setManagedOrgId] = useState('')
  const [activeOrg, setActiveOrg] = useState<OrganizationDto | null>(null)

  const create = useMutation({
    mutationFn: () => tenancyApi.createOrganization(orgName),
    onSuccess: (org) => {
      toast.success('Organization created', org.name)
      setActiveOrg(org)
      setOrgName('')
    },
    onError: (error) => toast.danger('Could not create organization', error instanceof Error ? error.message : undefined),
  })

  return (
    <div className="space-y-6">
      <OpsPageHeader
        eyebrow="Access"
        title="Organizations"
        description="Create organizations, manage membership and roles, and send invitations — full tenancy management backed by real endpoints."
      />

      <SectionCard icon={UserPlus} title="Create an organization">
        <div className="flex flex-wrap items-end gap-2">
          <div>
            <Label htmlFor="org-name">Name</Label>
            <Input id="org-name" value={orgName} onChange={(e) => setOrgName(e.target.value)} className="mt-1.5 w-64" />
          </div>
          <Button onClick={() => create.mutate()} disabled={!orgName || create.isPending}>
            {create.isPending ? 'Creating…' : 'Create organization'}
          </Button>
        </div>
      </SectionCard>

      {activeOrg && <OrganizationMembers organization={activeOrg} />}

      <SectionCard icon={Building2} title="Manage an existing organization" description="No directory endpoint exists yet — paste a known organization ID to manage it directly.">
        <div className="flex flex-wrap items-end gap-2">
          <div>
            <Label htmlFor="org-id">Organization ID</Label>
            <Input id="org-id" value={managedOrgId} onChange={(e) => setManagedOrgId(e.target.value)} className="mt-1.5 w-72 font-mono text-xs" />
          </div>
          <Button
            variant="secondary"
            onClick={() => setActiveOrg({ id: managedOrgId, name: managedOrgId, owner_id: '', created_at: new Date(0).toISOString() })}
            disabled={!managedOrgId}
          >
            Manage
          </Button>
        </div>
      </SectionCard>

      <SectionCard title="Not yet available">
        <BackendPendingState
          title="Organization directory, plans, usage & quotas, billing association"
          description="Organizations can be created and managed by ID, but there is no endpoint to list all organizations, and plan/usage/quota/billing association for an organization is not yet exposed — Billing & Revenue covers what exists for subscriptions today."
          recommendedEndpoint="GET /api/v1/admin/organizations"
        />
      </SectionCard>
    </div>
  )
}
