import { useQuery } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { Breadcrumbs } from '@/components/ui/breadcrumbs'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { tenancyApi } from '@/lib/api/tenancy'
import { useActiveOrgStore } from '@/stores/active-org-store'
import { toast } from '@/stores/toast-store'
import { queryClient } from '@/lib/query-client'

export default function OrganizationSettingsPage() {
  const { organizationId, organizationName, setOrganization } = useActiveOrgStore()
  const createForm = useForm<{ name: string }>()
  const inviteForm = useForm<{ email: string }>()

  const membersQuery = useQuery({
    queryKey: ['tenancy', 'members', organizationId],
    queryFn: () => tenancyApi.listMembers(organizationId!),
    enabled: Boolean(organizationId),
  })

  async function onCreate(values: { name: string }) {
    const org = await tenancyApi.createOrganization(values.name)
    setOrganization(org.id, org.name)
    toast.success('Organization created')
  }

  async function onInvite(values: { email: string }) {
    await tenancyApi.inviteMember(organizationId!, values.email)
    toast.success('Invitation sent', values.email)
    inviteForm.reset()
    void queryClient.invalidateQueries({ queryKey: ['tenancy', 'members', organizationId] })
  }

  return (
    <div className="flex flex-col gap-6 p-6">
      <div>
        <Breadcrumbs items={[{ label: 'Dashboard', to: '/app' }, { label: 'Organization Settings' }]} />
        <h1 className="mt-2 font-display text-2xl font-semibold text-text-primary">Organization Settings</h1>
      </div>

      {!organizationId ? (
        <Card className="max-w-md">
          <CardHeader>
            <CardTitle>Create an organization</CardTitle>
          </CardHeader>
          <CardContent>
            <form className="flex flex-col gap-3" onSubmit={createForm.handleSubmit(onCreate)}>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="org-name">Name</Label>
                <Input id="org-name" {...createForm.register('name', { required: true })} />
              </div>
              <Button type="submit" loading={createForm.formState.isSubmitting}>
                Create
              </Button>
            </form>
          </CardContent>
        </Card>
      ) : (
        <>
          <div className="flex items-center gap-2">
            <h2 className="font-display text-lg font-semibold text-text-primary">{organizationName}</h2>
            <Badge variant="neutral">org</Badge>
          </div>

          <Card className="max-w-lg">
            <CardHeader>
              <CardTitle>Members</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-2">
              {membersQuery.data?.map((member) => (
                <div key={member.user_id} className="flex items-center justify-between border-b border-border-subtle py-2 text-sm last:border-0">
                  <span className="font-mono text-text-primary">{member.user_id}</span>
                  <Badge variant="neutral">{member.role}</Badge>
                </div>
              ))}
              {membersQuery.data?.length === 0 && <p className="text-sm text-text-muted">No members yet.</p>}
            </CardContent>
          </Card>

          <Card className="max-w-lg">
            <CardHeader>
              <CardTitle>Invite a member</CardTitle>
            </CardHeader>
            <CardContent>
              <form className="flex gap-2" onSubmit={inviteForm.handleSubmit(onInvite)}>
                <Input placeholder="teammate@example.com" {...inviteForm.register('email', { required: true })} />
                <Button type="submit" loading={inviteForm.formState.isSubmitting}>
                  Invite
                </Button>
              </form>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  )
}
