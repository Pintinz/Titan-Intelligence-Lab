import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Users, ShieldCheck, KeyRound, Monitor } from 'lucide-react'
import { identityApi } from '@/lib/api/identity'
import type { Role } from '@/lib/api/types'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { OpsPageHeader, SectionCard, BackendPendingState } from '@/components/ops/ops-primitives'
import { toast } from '@/stores/toast-store'
import { useAuthStore } from '@/stores/auth-store'

const ROLE_LADDER: Array<{ role: Role; level: number; description: string }> = [
  { role: 'guest', level: 0, description: 'Unauthenticated or unverified access.' },
  { role: 'free', level: 1, description: 'Default tier after signup.' },
  { role: 'rewarded', level: 2, description: 'Unlocked via engagement rewards.' },
  { role: 'premium', level: 3, description: 'Paid subscriber tier.' },
  { role: 'moderator', level: 4, description: 'Community moderation privileges.' },
  { role: 'analyst', level: 5, description: 'Internal analytics access.' },
  { role: 'administrator', level: 6, description: 'Full Operations Center access.' },
  { role: 'super_administrator', level: 7, description: 'Highest privilege — every gate in the platform.' },
]

export default function UsersRolesPage() {
  const [userId, setUserId] = useState('')
  const [role, setRole] = useState<Role>('free')
  const profile = useAuthStore((s) => s.profile)

  const sessionsQuery = useQuery({ queryKey: ['identity', 'me', 'sessions'], queryFn: () => identityApi.mySessions() })
  const tokensQuery = useQuery({ queryKey: ['identity', 'me', 'tokens'], queryFn: () => identityApi.myTokens() })

  const changeRole = useMutation({
    mutationFn: () => identityApi.changeRole(userId, role),
    onSuccess: (user) => toast.success('Role updated', `${user.email} is now ${user.role}`),
    onError: (error) => toast.danger('Could not change role', error instanceof Error ? error.message : undefined),
  })

  return (
    <div className="space-y-6">
      <OpsPageHeader
        eyebrow="Access"
        title="Users & Roles"
        description="RBAC role assignment and the platform's permission ladder. Never bypasses the backend's own role checks — every change here goes through the real role-change endpoint."
      />

      <SectionCard icon={ShieldCheck} title="Change a user's role" description="Requires the target user's ID — assign any role up to your own privilege level.">
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <Label htmlFor="user-id">User ID</Label>
            <Input id="user-id" placeholder="uuid" value={userId} onChange={(e) => setUserId(e.target.value)} className="mt-1.5 w-72 font-mono text-xs" />
          </div>
          <div>
            <Label htmlFor="role-select">New role</Label>
            <Select value={role} onValueChange={(v) => setRole(v as Role)}>
              <SelectTrigger id="role-select" className="mt-1.5 w-48"><SelectValue /></SelectTrigger>
              <SelectContent>
                {ROLE_LADDER.map((r) => (
                  <SelectItem key={r.role} value={r.role} className="capitalize">{r.role.replace('_', ' ')}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <Button onClick={() => changeRole.mutate()} disabled={!userId || changeRole.isPending}>
            {changeRole.isPending ? 'Updating…' : 'Update role'}
          </Button>
        </div>
      </SectionCard>

      <SectionCard icon={Users} title="Permission ladder" description="TitanIQ's RBAC hierarchy — every role check in the backend compares numeric level, not identity, so any role above the required threshold passes.">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[480px] text-left text-sm">
            <thead className="text-xs uppercase tracking-wide text-text-muted">
              <tr><th className="pb-2 font-medium">Level</th><th className="pb-2 font-medium">Role</th><th className="pb-2 font-medium">Grants</th></tr>
            </thead>
            <tbody className="divide-y divide-border-subtle">
              {ROLE_LADDER.map((r) => (
                <tr key={r.role} className={profile?.role === r.role ? 'bg-accent-primary-muted/30' : undefined}>
                  <td className="py-2 font-mono text-text-muted">{r.level}</td>
                  <td className="py-2 font-medium capitalize text-text-primary">
                    {r.role.replace('_', ' ')}
                    {profile?.role === r.role && <span className="ml-2 text-[10px] font-medium uppercase tracking-wide text-accent-primary">You</span>}
                  </td>
                  <td className="py-2 text-text-secondary">{r.description}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </SectionCard>

      <div className="grid gap-6 lg:grid-cols-2">
        <SectionCard icon={Monitor} title="Your active sessions">
          {sessionsQuery.isPending && <Skeleton className="h-20" />}
          {sessionsQuery.data && sessionsQuery.data.length === 0 && <p className="text-sm text-text-secondary">No other active sessions.</p>}
          {sessionsQuery.data && sessionsQuery.data.length > 0 && (
            <ul className="space-y-1.5">
              {sessionsQuery.data.map((s) => (
                <li key={s.id} className="rounded border border-border-subtle px-2.5 py-1.5 text-xs">
                  <p className="text-text-primary">{s.device_label ?? 'Unknown device'} · {s.ip_address ?? 'unknown IP'}</p>
                  <p className="text-text-muted">Risk: {s.risk_level} · Last seen {new Date(s.last_seen_at).toLocaleString()}</p>
                </li>
              ))}
            </ul>
          )}
        </SectionCard>
        <SectionCard icon={KeyRound} title="Your personal access tokens">
          {tokensQuery.isPending && <Skeleton className="h-20" />}
          {tokensQuery.data && tokensQuery.data.length === 0 && <p className="text-sm text-text-secondary">No personal access tokens issued.</p>}
          {tokensQuery.data && tokensQuery.data.length > 0 && (
            <ul className="space-y-1.5">
              {tokensQuery.data.map((t) => (
                <li key={t.id} className="rounded border border-border-subtle px-2.5 py-1.5 text-xs">
                  <p className="text-text-primary">{t.name} {!t.is_active && '(revoked)'}</p>
                  <p className="text-text-muted">Scopes: {t.scopes.join(', ') || 'none'}</p>
                </li>
              ))}
            </ul>
          )}
        </SectionCard>
      </div>

      <SectionCard title="Not yet available">
        <BackendPendingState
          title="User directory, organizations-per-user, login history, and audit trail"
          description="There is no endpoint to list all users — role changes require already knowing a user's ID (from Supabase, support tooling, or the user themselves). Login history, failed-login tracking, password-reset history, and MFA status all exist in the identity domain's audit log conceptually, but no admin-facing read endpoint exposes them yet."
          recommendedEndpoint="GET /api/v1/admin/users?search=&role=&status= · GET /api/v1/admin/audit"
        />
      </SectionCard>
    </div>
  )
}
