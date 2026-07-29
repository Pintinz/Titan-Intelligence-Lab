import { useState } from 'react'
import { useAuthStore } from '@/stores/auth-store'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'

export default function SettingsPage() {
  const profile = useAuthStore((s) => s.profile)
  const [themeMode, setThemeMode] = useState<'dark' | 'light' | 'high-contrast'>('dark')
  const [emailNotifications, setEmailNotifications] = useState(true)

  return (
    <div className="mx-auto max-w-2xl space-y-8 p-4 lg:p-8">
      <div>
        <p className="font-telemetry text-xs font-semibold uppercase tracking-[0.16em] text-accent-primary">
          Account
        </p>
        <h1 className="mt-1 font-display text-2xl font-semibold text-text-primary">Settings</h1>
      </div>

      <Card className="p-5">
        <p className="font-display text-base font-semibold text-text-primary">Profile</p>
        <div className="mt-4 space-y-4">
          <div>
            <Label htmlFor="email">Email</Label>
            <Input id="email" value={profile?.email || ''} disabled className="mt-1" />
          </div>
          <div>
            <Label htmlFor="role">Role</Label>
            <Input id="role" value={profile?.role || ''} disabled className="mt-1" />
          </div>
          <div>
            <Label htmlFor="verified">Email verified</Label>
            <Input id="verified" value={profile?.email_verified ? 'Yes' : 'No'} disabled className="mt-1" />
          </div>
        </div>
      </Card>

      <Card className="p-5">
        <p className="font-display text-base font-semibold text-text-primary">Appearance</p>
        <div className="mt-4 space-y-4">
          <div>
            <Label htmlFor="theme">Theme</Label>
            <Select value={themeMode} onValueChange={(v) => setThemeMode(v as typeof themeMode)}>
              <SelectTrigger id="theme" className="mt-1"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="dark">Dark (default)</SelectItem>
                <SelectItem value="light">Light</SelectItem>
                <SelectItem value="high-contrast">High contrast</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <Button variant="secondary">Save appearance</Button>
        </div>
      </Card>

      <Card className="p-5">
        <p className="font-display text-base font-semibold text-text-primary">Notifications</p>
        <div className="mt-4 space-y-3">
          <label className="flex items-center gap-3">
            <input
              type="checkbox"
              checked={emailNotifications}
              onChange={(e) => setEmailNotifications(e.target.checked)}
              className="size-4 rounded border border-border-default"
            />
            <span className="text-sm text-text-secondary">Email me about market alerts and system updates</span>
          </label>
          <Button variant="secondary">Save notifications</Button>
        </div>
      </Card>

      <Card className="border-danger-muted bg-danger-muted/20 p-5">
        <p className="font-display text-base font-semibold text-danger">Danger zone</p>
        <p className="mt-2 text-sm text-text-secondary">Once you delete your account, there is no going back. Please be certain.</p>
        <Button variant="danger" className="mt-4">Delete account</Button>
      </Card>
    </div>
  )
}
