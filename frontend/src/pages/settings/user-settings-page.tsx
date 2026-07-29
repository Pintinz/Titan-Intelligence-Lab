import { useQuery } from '@tanstack/react-query'
import { Breadcrumbs } from '@/components/ui/breadcrumbs'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Label } from '@/components/ui/label'
import { identityApi } from '@/lib/api/identity'
import { toast } from '@/stores/toast-store'
import { useAuthStore } from '@/stores/auth-store'
import { useThemeStore, type Theme } from '@/stores/theme-store'
import { queryClient } from '@/lib/query-client'

export default function UserSettingsPage() {
  const profile = useAuthStore((s) => s.profile)
  const theme = useThemeStore((s) => s.theme)
  const setTheme = useThemeStore((s) => s.setTheme)
  const sessionsQuery = useQuery({ queryKey: ['identity', 'sessions'], queryFn: () => identityApi.mySessions() })
  const tokensQuery = useQuery({ queryKey: ['identity', 'tokens'], queryFn: () => identityApi.myTokens() })

  async function revokeSession(id: string) {
    await identityApi.revokeSession(id)
    toast.success('Session revoked')
    void queryClient.invalidateQueries({ queryKey: ['identity', 'sessions'] })
  }

  async function revokeToken(id: string) {
    await identityApi.revokeToken(id)
    toast.success('Token revoked')
    void queryClient.invalidateQueries({ queryKey: ['identity', 'tokens'] })
  }

  return (
    <div className="flex flex-col gap-6 p-6">
      <div>
        <Breadcrumbs items={[{ label: 'Dashboard', to: '/app' }, { label: 'Settings' }]} />
        <h1 className="mt-2 font-display text-2xl font-semibold text-text-primary">Profile Settings</h1>
      </div>

      <Card className="max-w-lg">
        <CardHeader>
          <CardTitle>Account</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-2 text-sm">
          <p className="text-text-primary">{profile?.email}</p>
          <Badge variant="accent" className="w-fit">
            {profile?.role}
          </Badge>
        </CardContent>
      </Card>

      <Card className="max-w-lg">
        <CardHeader>
          <CardTitle>Appearance</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-1.5">
          <Label htmlFor="theme-select">Theme</Label>
          <Select value={theme} onValueChange={(v) => setTheme(v as Theme)}>
            <SelectTrigger id="theme-select" className="w-56">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="dark">Dark</SelectItem>
              <SelectItem value="light">Light</SelectItem>
              <SelectItem value="high-contrast">High contrast</SelectItem>
            </SelectContent>
          </Select>
          <p className="text-xs text-text-muted">High contrast widens borders/text contrast and removes translucent surfaces.</p>
        </CardContent>
      </Card>

      <Card className="max-w-lg">
        <CardHeader>
          <CardTitle>Active sessions</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-2">
          {sessionsQuery.data?.map((session) => (
            <div key={session.id} className="flex items-center justify-between border-b border-border-subtle py-2 text-sm last:border-0">
              <div>
                <p className="text-text-primary">{session.device_label ?? 'Unknown device'}</p>
                <p className="text-xs text-text-muted">{session.ip_address} · {session.risk_level}</p>
              </div>
              <Button variant="ghost" size="sm" onClick={() => revokeSession(session.id)}>
                Revoke
              </Button>
            </div>
          ))}
          {sessionsQuery.data?.length === 0 && <p className="text-sm text-text-muted">No other active sessions.</p>}
        </CardContent>
      </Card>

      <Card className="max-w-lg">
        <CardHeader>
          <CardTitle>Personal access tokens</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-2">
          {tokensQuery.data?.map((token) => (
            <div key={token.id} className="flex items-center justify-between border-b border-border-subtle py-2 text-sm last:border-0">
              <div>
                <p className="text-text-primary">{token.name}</p>
                <p className="text-xs text-text-muted">{token.scopes.join(', ')}</p>
              </div>
              <Button variant="ghost" size="sm" onClick={() => revokeToken(token.id)}>
                Revoke
              </Button>
            </div>
          ))}
          {tokensQuery.data?.length === 0 && <p className="text-sm text-text-muted">No personal access tokens.</p>}
        </CardContent>
      </Card>
    </div>
  )
}
