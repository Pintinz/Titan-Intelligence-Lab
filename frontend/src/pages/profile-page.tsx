import { Link } from 'react-router-dom'
import { LogOut, Settings } from 'lucide-react'
import { useAuthStore } from '@/stores/auth-store'
import { InfinityLabel, InfinityPanel } from '@/components/infinity/primitives/panel'
import { InfinityButton } from '@/components/infinity/primitives/button'

/** Real account identity — distinct from Settings (preferences/configuration). Reuses the same
 * auth-store profile data Settings already displays; no new backend call. */
export default function ProfilePage() {
  const profile = useAuthStore((s) => s.profile)
  const signOut = useAuthStore((s) => s.signOut)

  if (!profile) return null

  const initial = profile.email.charAt(0).toUpperCase()

  return (
    <div className="mx-auto max-w-lg space-y-6">
      <div>
        <InfinityLabel tone="var(--infinity-signal)">Profile</InfinityLabel>
        <h2 className="mt-1 font-infinity-display text-lg font-semibold text-infinity-text-primary">Your account</h2>
      </div>

      <InfinityPanel tone="var(--infinity-signal)">
        <div className="flex items-center gap-4">
          <span
            className="flex size-14 shrink-0 items-center justify-center rounded-full bg-infinity-signal-muted font-infinity-mono text-xl font-medium text-infinity-signal"
            aria-hidden="true"
          >
            {initial}
          </span>
          <div className="min-w-0">
            <p className="truncate font-infinity-display text-[15px] font-semibold text-infinity-text-primary">
              {profile.email}
            </p>
            <p className="mt-0.5 font-infinity-mono text-[11px] capitalize text-infinity-text-muted">
              {profile.role.replace('_', ' ')} · {profile.email_verified ? 'Verified' : 'Unverified'}
            </p>
          </div>
        </div>
      </InfinityPanel>

      <div className="flex gap-2">
        <Link
          to="/app/settings"
          className="inline-flex h-9 items-center justify-center gap-2 whitespace-nowrap rounded-infinity-sm border border-infinity-border-default bg-infinity-ground-2 px-3.5 font-infinity-body text-[13px] font-medium text-infinity-text-primary transition-colors duration-100 hover:border-infinity-border-strong"
        >
          <Settings className="size-3.5" aria-hidden="true" /> Settings
        </Link>
        <InfinityButton type="button" variant="danger" size="sm" onClick={() => void signOut()}>
          <LogOut className="size-3.5" aria-hidden="true" /> Sign out
        </InfinityButton>
      </div>
    </div>
  )
}
