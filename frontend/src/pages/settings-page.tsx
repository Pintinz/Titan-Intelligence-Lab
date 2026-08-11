import { useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { LucideIcon } from 'lucide-react'
import {
  UserCircle,
  ShieldCheck,
  Palette,
  Bell,
  Trophy,
  SlidersHorizontal,
  Target,
  FileSearch,
  LayoutGrid,
  Monitor,
  Accessibility,
  Lock,
  CreditCard,
  KeyRound,
  Copy,
  Check,
  Plus,
  Wrench,
  ServerCog,
  FlaskConical,
  MonitorSmartphone,
  Waves,
  Fingerprint,
} from 'lucide-react'
import { useAuthStore } from '@/stores/auth-store'
import { useThemeStore, type Theme } from '@/stores/theme-store'
import { isAtLeast } from '@/lib/api/types'
import type { PersonalAccessTokenDto, SessionDto } from '@/lib/api/types'
import { identityApi } from '@/lib/api/identity'
import { toast } from '@/stores/toast-store'
import { cn } from '@/lib/cn'
import { InfinityLabel } from '@/components/infinity/primitives/panel'
import { InfinityButton } from '@/components/infinity/primitives/button'
import { StatusBadge } from '@/components/infinity/primitives/status-badge'
import { ComingSoonSetting } from '@/components/infinity/primitives/coming-soon-setting'
import { ConfirmDialog } from '@/components/infinity/primitives/confirm-dialog'

interface SettingsNavItem {
  id: string
  label: string
  icon: LucideIcon
}

interface SettingsNavGroup {
  label: string
  items: SettingsNavItem[]
}

const SETTINGS_GROUPS: SettingsNavGroup[] = [
  {
    label: 'Account',
    items: [
      { id: 'profile', label: 'Profile', icon: UserCircle },
      { id: 'security', label: 'Security', icon: ShieldCheck },
    ],
  },
  {
    label: 'Preferences',
    items: [
      { id: 'appearance', label: 'Appearance', icon: Palette },
      { id: 'notifications', label: 'Notifications', icon: Bell },
      { id: 'sports-coverage', label: 'Sports & Coverage', icon: Trophy },
      { id: 'default-experience', label: 'Default Experience', icon: SlidersHorizontal },
    ],
  },
  {
    label: 'Intelligence',
    items: [
      { id: 'prediction-preferences', label: 'Prediction Preferences', icon: Target },
      { id: 'evidence-explanation', label: 'Evidence & Explanation', icon: FileSearch },
      { id: 'data-display', label: 'Data Display', icon: LayoutGrid },
    ],
  },
  {
    label: 'Application',
    items: [
      { id: 'interface', label: 'Interface', icon: Monitor },
      { id: 'accessibility', label: 'Accessibility', icon: Accessibility },
      { id: 'privacy', label: 'Privacy', icon: Lock },
    ],
  },
  {
    label: 'Billing',
    items: [{ id: 'plan-usage', label: 'Plan & Usage', icon: CreditCard }],
  },
]

const ADMIN_GROUP: SettingsNavGroup = {
  label: 'Administration',
  items: [{ id: 'administration', label: 'Administration', icon: Wrench }],
}

const SECTION_META: Record<string, { title: string; description: string }> = {
  profile: { title: 'Profile', description: 'Your TitanIQ account identity.' },
  security: { title: 'Security', description: 'Active sessions and personal access tokens on your account.' },
  appearance: { title: 'Appearance', description: 'Choose how TitanIQ looks across your devices.' },
  notifications: { title: 'Notifications', description: 'What TitanIQ alerts you about, and what stays fixed today.' },
  'sports-coverage': { title: 'Sports & Coverage', description: 'What TitanIQ covers, and how to focus on what matters to you.' },
  'default-experience': { title: 'Default Experience', description: 'The view TitanIQ opens to and how matches are ordered.' },
  'prediction-preferences': { title: 'Prediction Preferences', description: 'How published predictions are ranked today.' },
  'evidence-explanation': { title: 'Evidence & Explanation', description: 'How much evidence detail predictions show.' },
  'data-display': { title: 'Data Display', description: 'Units, precision, and formatting for intelligence data.' },
  interface: { title: 'Interface', description: 'Layout, theme, and motion behavior.' },
  accessibility: { title: 'Accessibility', description: 'Motion, contrast, and assistive preferences.' },
  privacy: { title: 'Privacy', description: 'Data visibility and where it’s managed.' },
  'plan-usage': { title: 'Plan & Usage', description: 'Your TitanIQ plan and billing status.' },
  administration: { title: 'Administration', description: 'Operational tools available to TitanIQ administrators.' },
}

function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return 'Never'
  return new Date(iso).toLocaleString(undefined, { month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit' })
}

/**
 * A settings-navigation-scoped control surface — Profile, Security, and Appearance are real
 * (identityApi sessions/tokens, useThemeStore); every other section states its current, fixed
 * platform behavior and what's planned, through one consistent status vocabulary
 * (StatusBadge/ComingSoonSetting) rather than a repeated "Not available yet" panel. One section
 * is active at a time — a persistent left rail on desktop, a top selector on mobile — rather than
 * one long scroll.
 */
export default function SettingsPage() {
  const profile = useAuthStore((s) => s.profile)
  const isAdmin = !!profile && isAtLeast(profile.role, 'administrator')
  const groups = isAdmin ? [...SETTINGS_GROUPS, ADMIN_GROUP] : SETTINGS_GROUPS
  const [activeId, setActiveId] = useState('profile')
  const meta = SECTION_META[activeId] ?? SECTION_META.profile

  return (
    <div className="mx-auto max-w-[1160px]">
      <div className="mb-6">
        <InfinityLabel tone="var(--infinity-signal)">Settings</InfinityLabel>
        <h1 className="mt-1 font-infinity-display text-xl font-semibold text-infinity-text-primary">Settings</h1>
        <p className="mt-1 max-w-xl text-[13px] text-infinity-text-secondary">
          Manage your TitanIQ account, intelligence preferences, and application behavior.
        </p>
      </div>

      <div className="lg:hidden">
        <label htmlFor="settings-section-select" className="sr-only">
          Settings section
        </label>
        <select
          id="settings-section-select"
          value={activeId}
          onChange={(e) => setActiveId(e.target.value)}
          className="h-10 w-full rounded-infinity-sm border border-infinity-border-default bg-infinity-ground-2 px-3 font-infinity-body text-[13px] text-infinity-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-infinity-signal"
        >
          {groups.map((group) => (
            <optgroup key={group.label} label={group.label.toUpperCase()}>
              {group.items.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.label}
                </option>
              ))}
            </optgroup>
          ))}
        </select>
      </div>

      <div className="mt-6 grid gap-8 lg:grid-cols-[220px_1fr]">
        <nav aria-label="Settings sections" className="hidden lg:block">
          <div className="sticky top-6 space-y-5">
            {groups.map((group) => (
              <div key={group.label}>
                <InfinityLabel className="px-2.5">{group.label}</InfinityLabel>
                <ul className="mt-2 space-y-0.5">
                  {group.items.map((item) => {
                    const active = item.id === activeId
                    return (
                      <li key={item.id}>
                        <button
                          type="button"
                          onClick={() => setActiveId(item.id)}
                          aria-current={active ? 'true' : undefined}
                          className={cn(
                            'flex w-full items-center gap-2.5 rounded-infinity-sm border-l-2 px-2.5 py-1.5 text-left font-infinity-body text-[13px] transition-colors duration-150',
                            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-infinity-signal',
                            active
                              ? 'border-infinity-signal bg-infinity-signal-muted text-infinity-text-primary font-medium'
                              : 'border-transparent text-infinity-text-secondary hover:bg-infinity-ground-2 hover:text-infinity-text-primary',
                          )}
                        >
                          <item.icon className="size-3.5 shrink-0" aria-hidden="true" />
                          <span className="truncate">{item.label}</span>
                        </button>
                      </li>
                    )
                  })}
                </ul>
              </div>
            ))}
          </div>
        </nav>

        <div className="min-w-0 pb-16">
          <SectionHeader title={meta.title} description={meta.description} />
          <div className="mt-4">{renderSection(activeId, { isAdmin, onNavigate: setActiveId })}</div>
        </div>
      </div>
    </div>
  )
}

function renderSection(id: string, ctx: { isAdmin: boolean; onNavigate: (id: string) => void }) {
  switch (id) {
    case 'profile':
      return <ProfileSection />
    case 'security':
      return <SecuritySection />
    case 'appearance':
      return <AppearanceSection />
    case 'notifications':
      return <NotificationsSection />
    case 'sports-coverage':
      return <SportsCoverageSection />
    case 'default-experience':
      return <DefaultExperienceSection />
    case 'prediction-preferences':
      return <PredictionPreferencesSection />
    case 'evidence-explanation':
      return <EvidenceExplanationSection />
    case 'data-display':
      return <DataDisplaySection />
    case 'interface':
      return <InterfaceSection onNavigate={ctx.onNavigate} />
    case 'accessibility':
      return <AccessibilitySection />
    case 'privacy':
      return <PrivacySection onNavigate={ctx.onNavigate} />
    case 'plan-usage':
      return <BillingSection />
    case 'administration':
      return ctx.isAdmin ? <AdministrationSection /> : null
    default:
      return null
  }
}

function SectionHeader({ title, description }: { title: string; description: string }) {
  return (
    <div>
      <h2 className="font-infinity-display text-[16px] font-semibold text-infinity-text-primary">{title}</h2>
      <p className="mt-0.5 text-[13px] text-infinity-text-secondary">{description}</p>
    </div>
  )
}

function CheckItem({ label }: { label: string }) {
  return (
    <li className="flex items-center gap-2 text-[13px] text-infinity-text-secondary">
      <Check className="size-3.5 shrink-0 text-infinity-success" aria-hidden="true" />
      {label}
    </li>
  )
}

function Field({ label, value, className }: { label: string; value: string; className?: string }) {
  return (
    <div>
      <dt className="font-infinity-mono text-[10.5px] uppercase tracking-[0.06em] text-infinity-text-muted">{label}</dt>
      <dd className={cn('mt-0.5 truncate font-infinity-body text-[13px] text-infinity-text-primary', className)}>{value}</dd>
    </div>
  )
}

/**
 * The one card shell every settings surface uses — same parameters as the Appearance theme
 * cards (rounded-infinity-md border bg-infinity-ground-1 p-3), `tone="signal"` matching that
 * same component's active-card treatment for the rare panel that needs to stand out (e.g. a
 * just-created token). No corner-tick decoration — settings is a control surface, not an
 * evidence panel.
 */
function SettingsCard({ tone = 'default', className, children }: { tone?: 'default' | 'signal'; className?: string; children: ReactNode }) {
  return (
    <div
      className={cn(
        'rounded-infinity-md border p-3',
        tone === 'signal' ? 'border-infinity-signal bg-infinity-signal-muted' : 'border-infinity-border-default bg-infinity-ground-1',
        className,
      )}
    >
      {children}
    </div>
  )
}

// ---------------------------------------------------------------------------------------------
// Profile — real, from useAuthStore
// ---------------------------------------------------------------------------------------------

function ProfileSection() {
  const profile = useAuthStore((s) => s.profile)
  if (!profile) return null

  const initial = profile.email.charAt(0).toUpperCase()

  return (
    <SettingsCard className="p-4">
      <div className="flex items-start gap-4">
        <span
          className="flex size-12 shrink-0 items-center justify-center rounded-full bg-infinity-signal-muted font-infinity-mono text-lg font-medium text-infinity-signal"
          aria-hidden="true"
        >
          {initial}
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate font-infinity-display text-[15px] font-semibold text-infinity-text-primary">{profile.email}</p>
          <p className="mt-0.5 font-infinity-mono text-[11px] capitalize text-infinity-text-muted">{profile.role.replace('_', ' ')}</p>
          <div className="mt-2.5 flex flex-wrap gap-x-4 gap-y-1">
            <span className="flex items-center gap-1.5 text-[12px] text-infinity-text-secondary">
              <span
                className="size-1.5 rounded-full"
                style={{ backgroundColor: profile.email_verified ? 'var(--infinity-success)' : 'var(--infinity-text-muted)' }}
                aria-hidden="true"
              />
              {profile.email_verified ? 'Email verified' : 'Email unverified'}
            </span>
            <span className="flex items-center gap-1.5 text-[12px] capitalize text-infinity-text-secondary">
              <span
                className="size-1.5 rounded-full"
                style={{ backgroundColor: profile.status === 'active' ? 'var(--infinity-success)' : 'var(--infinity-text-muted)' }}
                aria-hidden="true"
              />
              Account {profile.status}
            </span>
          </div>
        </div>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-4 border-t border-infinity-border-hairline pt-4">
        <Field label="Member since" value={formatDateTime(profile.created_at)} />
        <Field label="Last sign-in" value={formatDateTime(profile.last_login_at)} />
      </div>

      <p className="mt-4 text-[11.5px] leading-relaxed text-infinity-text-muted">
        These fields are managed by your TitanIQ account and are currently read-only.
      </p>
    </SettingsCard>
  )
}

// ---------------------------------------------------------------------------------------------
// Security — real, via identityApi
// ---------------------------------------------------------------------------------------------

function SkeletonRow() {
  return (
    <SettingsCard className="animate-pulse">
      <div className="h-3 w-40 rounded-full bg-infinity-ground-2" />
      <div className="mt-2 h-2.5 w-56 rounded-full bg-infinity-ground-2" />
    </SettingsCard>
  )
}

function SecuritySection() {
  const queryClient = useQueryClient()
  const sessionsQuery = useQuery({ queryKey: ['identity', 'sessions'], queryFn: () => identityApi.mySessions() })
  const tokensQuery = useQuery({ queryKey: ['identity', 'tokens'], queryFn: () => identityApi.myTokens() })
  const profile = useAuthStore((s) => s.profile)

  const [sessionToRevoke, setSessionToRevoke] = useState<SessionDto | null>(null)
  const [tokenToRevoke, setTokenToRevoke] = useState<PersonalAccessTokenDto | null>(null)

  const revokeSession = useMutation({
    mutationFn: (id: string) => identityApi.revokeSession(id),
    onSuccess: () => {
      toast.success('Session revoked')
      setSessionToRevoke(null)
      void queryClient.invalidateQueries({ queryKey: ['identity', 'sessions'] })
    },
    onError: () => toast.danger('Could not revoke session'),
  })

  const revokeToken = useMutation({
    mutationFn: (id: string) => identityApi.revokeToken(id),
    onSuccess: () => {
      toast.success('Token revoked')
      setTokenToRevoke(null)
      void queryClient.invalidateQueries({ queryKey: ['identity', 'tokens'] })
    },
    onError: () => toast.danger('Could not revoke token'),
  })

  const [tokenName, setTokenName] = useState('')
  const [revealedToken, setRevealedToken] = useState<{ name: string; raw: string } | null>(null)
  const [copied, setCopied] = useState(false)

  const createToken = useMutation({
    mutationFn: (name: string) => identityApi.createToken(name, []),
    onSuccess: (result) => {
      setRevealedToken({ name: result.name, raw: result.raw_token })
      setTokenName('')
      void queryClient.invalidateQueries({ queryKey: ['identity', 'tokens'] })
    },
    onError: () => toast.danger('Could not create token'),
  })

  function handleCopy(raw: string) {
    void navigator.clipboard.writeText(raw)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  return (
    <div className="space-y-6">
      <div>
        <p className="mb-2 font-infinity-body text-[12px] font-medium uppercase tracking-[0.04em] text-infinity-text-muted">Account security</p>
        <SettingsCard className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div className="flex items-start gap-2.5">
            <Fingerprint className="mt-0.5 size-4 shrink-0 text-infinity-text-muted" aria-hidden="true" />
            <div>
              <p className="font-infinity-body text-[13px] font-medium text-infinity-text-primary">Email</p>
              <p className="mt-0.5 flex items-center gap-1.5 text-[12px] text-infinity-text-secondary">
                <span
                  className="size-1.5 rounded-full"
                  style={{ backgroundColor: profile?.email_verified ? 'var(--infinity-success)' : 'var(--infinity-text-muted)' }}
                  aria-hidden="true"
                />
                {profile?.email_verified ? 'Verified' : 'Unverified'}
              </p>
            </div>
          </div>
          <div className="flex items-start gap-2.5">
            <Lock className="mt-0.5 size-4 shrink-0 text-infinity-text-muted" aria-hidden="true" />
            <div>
              <p className="font-infinity-body text-[13px] font-medium text-infinity-text-primary">Password</p>
              <p className="mt-0.5 text-[12px] text-infinity-text-secondary">Managed by TitanIQ authentication</p>
            </div>
          </div>
        </SettingsCard>
      </div>

      <div>
        <p className="mb-2 font-infinity-body text-[12px] font-medium uppercase tracking-[0.04em] text-infinity-text-muted">Active sessions</p>
        {sessionsQuery.isPending && (
          <div className="space-y-2">
            <SkeletonRow />
            <SkeletonRow />
          </div>
        )}
        {sessionsQuery.isError && <p className="text-[13px] text-infinity-danger">Couldn't load sessions.</p>}
        {sessionsQuery.data && sessionsQuery.data.length === 0 && <p className="text-[13px] text-infinity-text-muted">No active sessions.</p>}
        <div className="space-y-2">
          {sessionsQuery.data?.map((session) => (
            <SettingsCard key={session.id} className="p-3">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="min-w-0">
                  <p className="truncate font-infinity-body text-[13px] font-medium text-infinity-text-primary">
                    {session.device_label ?? 'Unknown device'}
                  </p>
                  <p className="mt-0.5 truncate font-infinity-mono text-[11px] text-infinity-text-muted">
                    {session.ip_address ?? 'Unknown IP'} · Last active {formatDateTime(session.last_seen_at)}
                  </p>
                </div>
                <InfinityButton type="button" variant="danger" size="sm" onClick={() => setSessionToRevoke(session)}>
                  Revoke
                </InfinityButton>
              </div>
            </SettingsCard>
          ))}
        </div>
      </div>

      <div>
        <p className="mb-2 font-infinity-body text-[12px] font-medium uppercase tracking-[0.04em] text-infinity-text-muted">Personal access tokens</p>
        {tokensQuery.isPending && (
          <div className="space-y-2">
            <SkeletonRow />
          </div>
        )}
        {tokensQuery.isError && <p className="text-[13px] text-infinity-danger">Couldn't load tokens.</p>}
        <div className="space-y-2">
          {tokensQuery.data?.map((token) => (
            <SettingsCard key={token.id} className="p-3">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <KeyRound className="size-3.5 shrink-0 text-infinity-text-muted" aria-hidden="true" />
                    <p className="truncate font-infinity-body text-[13px] font-medium text-infinity-text-primary">{token.name}</p>
                    {!token.is_active && (
                      <span className="rounded-full border border-infinity-border-default px-1.5 py-0.5 font-infinity-mono text-[9px] uppercase tracking-[0.06em] text-infinity-text-muted">
                        Revoked
                      </span>
                    )}
                  </div>
                  <p className="mt-0.5 truncate font-infinity-mono text-[11px] text-infinity-text-muted">
                    Last used {formatDateTime(token.last_used_at)} · Created {formatDateTime(token.created_at)}
                  </p>
                </div>
                {token.is_active && (
                  <InfinityButton type="button" variant="danger" size="sm" onClick={() => setTokenToRevoke(token)}>
                    Revoke
                  </InfinityButton>
                )}
              </div>
            </SettingsCard>
          ))}
          {tokensQuery.data && tokensQuery.data.length === 0 && <p className="text-[13px] text-infinity-text-muted">No personal access tokens yet.</p>}
        </div>

        {revealedToken && (
          <SettingsCard tone="signal" className="mt-2">
            <p className="font-infinity-body text-[13px] font-medium text-infinity-text-primary">
              &ldquo;{revealedToken.name}&rdquo; created — copy it now
            </p>
            <p className="mt-1 text-[12px] text-infinity-text-secondary">This token won't be shown again.</p>
            <div className="mt-2 flex items-center gap-2">
              <code className="min-w-0 flex-1 truncate rounded-infinity-sm bg-infinity-ground-2 px-2.5 py-1.5 font-infinity-mono text-[12px] text-infinity-text-primary">
                {revealedToken.raw}
              </code>
              <InfinityButton type="button" variant="secondary" size="sm" onClick={() => handleCopy(revealedToken.raw)}>
                {copied ? <Check className="size-3.5" aria-hidden="true" /> : <Copy className="size-3.5" aria-hidden="true" />}
                {copied ? 'Copied' : 'Copy'}
              </InfinityButton>
            </div>
          </SettingsCard>
        )}

        <form
          className="mt-3 flex flex-wrap items-center gap-2"
          onSubmit={(e) => {
            e.preventDefault()
            if (!tokenName.trim()) return
            createToken.mutate(tokenName.trim())
          }}
        >
          <input
            value={tokenName}
            onChange={(e) => setTokenName(e.target.value)}
            placeholder='Token name, e.g. "CI pipeline"'
            className="h-9 min-w-0 flex-1 rounded-infinity-sm border border-infinity-border-default bg-infinity-ground-2 px-3 font-infinity-body text-[13px] text-infinity-text-primary placeholder:text-infinity-text-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-infinity-signal"
          />
          <InfinityButton type="submit" variant="secondary" size="sm" disabled={!tokenName.trim() || createToken.isPending}>
            <Plus className="size-3.5" aria-hidden="true" /> Create token
          </InfinityButton>
        </form>
      </div>

      <ConfirmDialog
        open={!!sessionToRevoke}
        onOpenChange={(open) => !open && setSessionToRevoke(null)}
        title="Revoke this session?"
        description={`This immediately signs out "${sessionToRevoke?.device_label ?? 'this device'}". It will need to sign in again to access TitanIQ.`}
        confirmLabel="Revoke session"
        isPending={revokeSession.isPending}
        onConfirm={() => sessionToRevoke && revokeSession.mutate(sessionToRevoke.id)}
      />
      <ConfirmDialog
        open={!!tokenToRevoke}
        onOpenChange={(open) => !open && setTokenToRevoke(null)}
        title="Revoke this token?"
        description={`"${tokenToRevoke?.name}" will stop working immediately for any integration using it. This can't be undone.`}
        confirmLabel="Revoke token"
        isPending={revokeToken.isPending}
        onConfirm={() => tokenToRevoke && revokeToken.mutate(tokenToRevoke.id)}
      />
    </div>
  )
}

// ---------------------------------------------------------------------------------------------
// Appearance — real, via useThemeStore
// ---------------------------------------------------------------------------------------------

const THEME_PREVIEW_PALETTES: Record<Theme, { ground0: string; ground1: string; ground2: string; signal: string; text: string; border: string; borderHairline: string }> = {
  dark: { ground0: '#05070a', ground1: '#0a0e14', ground2: '#10151d', signal: '#00d1ff', text: '#eef3f8', border: '#29323f', borderHairline: '#1c242f' },
  light: { ground0: '#ffffff', ground1: '#f4f6f8', ground2: '#ffffff', signal: '#0082a8', text: '#0b1016', border: '#d4d9df', borderHairline: '#e6e9ed' },
  'high-contrast': { ground0: '#000000', ground1: '#0a0a0a', ground2: '#141414', signal: '#4de0ff', text: '#ffffff', border: '#5f5f5f', borderHairline: '#3d3d3d' },
}

const THEME_OPTIONS: { value: Theme; label: string; description: string }[] = [
  { value: 'dark', label: 'Dark', description: 'Graphite TitanIQ interface, high contrast evidence surfaces.' },
  { value: 'light', label: 'Light', description: 'Same visual language with lighter surfaces.' },
  { value: 'high-contrast', label: 'High contrast', description: 'Maximum visual separation, optimized for accessibility.' },
]

function ThemePreviewSwatch({ theme }: { theme: Theme }) {
  const p = THEME_PREVIEW_PALETTES[theme]
  return (
    <div className="h-14 w-full overflow-hidden rounded-infinity-sm border" style={{ borderColor: p.border, backgroundColor: p.ground1 }} aria-hidden="true">
      <div className="flex h-4 items-center gap-1 border-b px-2" style={{ borderColor: p.borderHairline, backgroundColor: p.ground0 }}>
        <span className="size-1.5 rounded-full" style={{ backgroundColor: p.signal }} />
        <span className="h-1 w-10 rounded-full" style={{ backgroundColor: p.border }} />
      </div>
      <div className="flex gap-1.5 p-2">
        <span className="size-6 shrink-0 rounded-[3px]" style={{ backgroundColor: p.ground2, border: `1px solid ${p.borderHairline}` }} />
        <div className="min-w-0 flex-1 space-y-1.5 pt-0.5">
          <span className="block h-1 w-full rounded-full" style={{ backgroundColor: p.text, opacity: 0.8 }} />
          <span className="block h-1 w-2/3 rounded-full" style={{ backgroundColor: p.signal }} />
        </div>
      </div>
    </div>
  )
}

function AppearanceSection() {
  const theme = useThemeStore((s) => s.theme)
  const setTheme = useThemeStore((s) => s.setTheme)

  return (
    <div className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-3">
        {THEME_OPTIONS.map((option) => {
          const active = theme === option.value
          return (
            <button
              key={option.value}
              type="button"
              onClick={() => setTheme(option.value)}
              aria-pressed={active}
              className={cn(
                'rounded-infinity-md border p-3 text-left transition-colors duration-150',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-infinity-signal',
                active
                  ? 'border-infinity-signal bg-infinity-signal-muted'
                  : 'border-infinity-border-default bg-infinity-ground-1 hover:border-infinity-border-strong',
              )}
            >
              <ThemePreviewSwatch theme={option.value} />
              <div className="mt-2.5 flex items-center justify-between">
                <p className="font-infinity-body text-[13px] font-medium text-infinity-text-primary">{option.label}</p>
                {active && <Check className="size-3.5 shrink-0 text-infinity-signal" aria-hidden="true" />}
              </div>
              <p className="mt-1 text-[11.5px] leading-relaxed text-infinity-text-muted">{option.description}</p>
            </button>
          )
        })}
      </div>
      <p className="text-[11.5px] text-infinity-text-muted">Applies immediately — no save step.</p>
    </div>
  )
}

// ---------------------------------------------------------------------------------------------
// Notifications — real current behavior, customization coming soon
// ---------------------------------------------------------------------------------------------

function NotificationsSection() {
  return (
    <div className="space-y-4">
      <SettingsCard>
        <div className="flex items-center gap-2">
          <p className="font-infinity-body text-[12px] font-medium uppercase tracking-[0.04em] text-infinity-text-muted">Current behavior</p>
          <StatusBadge status="available" />
        </div>
        <p className="mt-2 text-[13px] text-infinity-text-secondary">TitanIQ currently delivers alerts for everything you follow.</p>
        <ul className="mt-3 space-y-1.5">
          <CheckItem label="Match kickoff" />
          <CheckItem label="Final result" />
          <CheckItem label="Prediction changes" />
        </ul>
      </SettingsCard>

      <ComingSoonSetting
        icon={Bell}
        title="Customization"
        description="Per-event notification controls — muting a specific alert type, or adjusting delivery timing — aren't configurable yet."
      />
    </div>
  )
}

// ---------------------------------------------------------------------------------------------
// Sports & Coverage — global coverage is real; per-sport preference is not
// ---------------------------------------------------------------------------------------------

const SUPPORTED_SPORTS = ['Football', 'Basketball', 'Baseball', 'Table Tennis']

function SportsCoverageSection() {
  return (
    <div className="space-y-4">
      <SettingsCard>
        <p className="font-infinity-body text-[12px] font-medium uppercase tracking-[0.04em] text-infinity-text-muted">Supported sports</p>
        <div className="mt-2.5 flex flex-wrap gap-2">
          {SUPPORTED_SPORTS.map((sport) => (
            <span
              key={sport}
              className="rounded-full border border-infinity-border-default bg-infinity-ground-2 px-3 py-1 font-infinity-body text-[12.5px] font-medium text-infinity-text-secondary"
            >
              {sport}
            </span>
          ))}
        </div>
      </SettingsCard>

      <SettingsCard>
        <div className="flex flex-wrap items-center gap-2">
          <p className="font-infinity-body text-[13px] font-medium text-infinity-text-primary">Coverage is currently global</p>
          <StatusBadge status="managed-elsewhere" />
        </div>
        <p className="mt-1.5 text-[13px] leading-relaxed text-infinity-text-secondary">
          TitanIQ automatically surfaces intelligence across every supported sport. Manage what matters to you using Watchlist.
        </p>
        <Link
          to="/app/watchlist"
          className="mt-3 inline-flex h-8 items-center justify-center gap-1.5 whitespace-nowrap rounded-infinity-sm border border-infinity-border-default bg-infinity-ground-2 px-3 font-infinity-body text-[12.5px] font-medium text-infinity-text-primary transition-colors duration-100 hover:border-infinity-border-strong"
        >
          Open Watchlist
        </Link>
      </SettingsCard>
    </div>
  )
}

// ---------------------------------------------------------------------------------------------
// Default Experience — coming soon
// ---------------------------------------------------------------------------------------------

function DefaultExperienceSection() {
  return (
    <ComingSoonSetting
      icon={SlidersHorizontal}
      title="Default Experience"
      description="TitanIQ currently opens using the standard Mission Control experience. Default landing page, match sorting, and competition sorting aren't configurable yet."
    />
  )
}

// ---------------------------------------------------------------------------------------------
// Intelligence settings — describe real ranking/evidence behavior, link to where it lives
// ---------------------------------------------------------------------------------------------

function PredictionPreferencesSection() {
  return (
    <div className="space-y-4">
      <SettingsCard>
        <div className="flex items-center gap-2">
          <p className="font-infinity-body text-[12px] font-medium uppercase tracking-[0.04em] text-infinity-text-muted">Available today</p>
          <StatusBadge status="available" />
        </div>
        <p className="mt-2 text-[13px] text-infinity-text-secondary">
          TitanIQ currently ranks published predictions using the platform's intelligence engine.
        </p>
        <ul className="mt-3 space-y-1.5">
          <CheckItem label="Confidence ranking" />
          <CheckItem label="Market ranking" />
          <CheckItem label="Evidence drivers" />
        </ul>
        <Link
          to="/app/picks"
          className="mt-3 inline-flex h-8 items-center justify-center gap-1.5 whitespace-nowrap rounded-infinity-sm border border-infinity-border-default bg-infinity-ground-2 px-3 font-infinity-body text-[12.5px] font-medium text-infinity-text-primary transition-colors duration-100 hover:border-infinity-border-strong"
        >
          Explore AI Picks
        </Link>
      </SettingsCard>

      <ComingSoonSetting icon={Target} title="Personal prediction weighting" description="Tuning which markets and confidence thresholds matter most to you isn't available yet." />
    </div>
  )
}

function EvidenceExplanationSection() {
  return (
    <div className="space-y-4">
      <SettingsCard>
        <div className="flex items-center gap-2">
          <p className="font-infinity-body text-[12px] font-medium uppercase tracking-[0.04em] text-infinity-text-muted">Available today</p>
          <StatusBadge status="available" />
        </div>
        <p className="mt-2 text-[13px] text-infinity-text-secondary">TitanIQ currently exposes full evidence drivers for every published prediction.</p>
        <ul className="mt-3 space-y-1.5">
          <CheckItem label="Model features" />
          <CheckItem label="Confidence score" />
          <CheckItem label="Probability" />
          <CheckItem label="Supporting drivers" />
          <CheckItem label="Opposing drivers, where available" />
        </ul>
        <Link
          to="/app/insights"
          className="mt-3 inline-flex h-8 items-center justify-center gap-1.5 whitespace-nowrap rounded-infinity-sm border border-infinity-border-default bg-infinity-ground-2 px-3 font-infinity-body text-[12.5px] font-medium text-infinity-text-primary transition-colors duration-100 hover:border-infinity-border-strong"
        >
          Open Intelligence Workspace
        </Link>
      </SettingsCard>

      <ComingSoonSetting icon={FileSearch} title="Personal evidence density" description="Choosing how much evidence detail shows by default isn't configurable yet." />
    </div>
  )
}

function DataDisplaySection() {
  return (
    <ComingSoonSetting
      icon={LayoutGrid}
      title="Data Display"
      description="TitanIQ currently uses the platform's standard analytical formatting. Density, numeric precision, unit preferences, and advanced display formatting aren't configurable yet."
    />
  )
}

// ---------------------------------------------------------------------------------------------
// Application settings
// ---------------------------------------------------------------------------------------------

function InterfaceSection({ onNavigate }: { onNavigate: (id: string) => void }) {
  return (
    <div className="space-y-3">
      <SettingsCard className="p-3.5">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-start gap-2.5">
            <Palette className="mt-0.5 size-4 shrink-0 text-infinity-text-muted" aria-hidden="true" />
            <div>
              <p className="font-infinity-body text-[13px] font-medium text-infinity-text-primary">Theme</p>
              <p className="mt-0.5 text-[12.5px] text-infinity-text-secondary">Managed under Appearance.</p>
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <StatusBadge status="managed-elsewhere" />
            <button type="button" onClick={() => onNavigate('appearance')} className="font-infinity-body text-[12px] font-medium text-infinity-signal hover:underline">
              Go
            </button>
          </div>
        </div>
      </SettingsCard>

      <SettingsCard className="p-3.5">
        <div className="flex items-start gap-2.5">
          <MonitorSmartphone className="mt-0.5 size-4 shrink-0 text-infinity-text-muted" aria-hidden="true" />
          <div className="flex-1">
            <div className="flex items-center gap-2">
              <p className="font-infinity-body text-[13px] font-medium text-infinity-text-primary">Layout</p>
              <StatusBadge status="not-configurable" />
            </div>
            <p className="mt-0.5 text-[12.5px] text-infinity-text-secondary">TitanIQ automatically adapts between desktop, tablet, and mobile.</p>
          </div>
        </div>
      </SettingsCard>

      <SettingsCard className="p-3.5">
        <div className="flex items-start gap-2.5">
          <Waves className="mt-0.5 size-4 shrink-0 text-infinity-text-muted" aria-hidden="true" />
          <div className="flex-1">
            <div className="flex items-center gap-2">
              <p className="font-infinity-body text-[13px] font-medium text-infinity-text-primary">Motion</p>
              <StatusBadge status="not-configurable" />
            </div>
            <p className="mt-0.5 text-[12.5px] text-infinity-text-secondary">TitanIQ respects your operating system's reduced-motion preference.</p>
          </div>
        </div>
      </SettingsCard>

      <ComingSoonSetting icon={LayoutGrid} title="Interface density" description="A compact/comfortable density toggle isn't available yet." />
    </div>
  )
}

function AccessibilitySection() {
  return (
    <div className="space-y-4">
      <SettingsCard>
        <div className="flex items-center gap-2">
          <p className="font-infinity-body text-[12px] font-medium uppercase tracking-[0.04em] text-infinity-text-muted">TitanIQ automatically respects</p>
          <StatusBadge status="available" />
        </div>
        <ul className="mt-3 space-y-1.5">
          <CheckItem label="Reduced-motion preferences" />
          <CheckItem label="Keyboard navigation" />
          <CheckItem label="System contrast preferences, where supported" />
        </ul>
      </SettingsCard>

      <ComingSoonSetting
        icon={Accessibility}
        title="Dedicated assistive controls"
        description="Dedicated contrast controls, font scaling, and additional assistive preferences aren't available yet."
      />
    </div>
  )
}

function PrivacySection({ onNavigate }: { onNavigate: (id: string) => void }) {
  return (
    <div className="space-y-3">
      <SettingsCard className="p-3.5">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-start gap-2.5">
            <ShieldCheck className="mt-0.5 size-4 shrink-0 text-infinity-text-muted" aria-hidden="true" />
            <div>
              <p className="font-infinity-body text-[13px] font-medium text-infinity-text-primary">Session management</p>
              <p className="mt-0.5 text-[12.5px] text-infinity-text-secondary">Available under Security.</p>
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <StatusBadge status="managed-elsewhere" />
            <button type="button" onClick={() => onNavigate('security')} className="font-infinity-body text-[12px] font-medium text-infinity-signal hover:underline">
              Go
            </button>
          </div>
        </div>
      </SettingsCard>

      <SettingsCard className="p-3.5">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-start gap-2.5">
            <KeyRound className="mt-0.5 size-4 shrink-0 text-infinity-text-muted" aria-hidden="true" />
            <div>
              <p className="font-infinity-body text-[13px] font-medium text-infinity-text-primary">Personal access tokens</p>
              <p className="mt-0.5 text-[12.5px] text-infinity-text-secondary">Available under Security.</p>
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <StatusBadge status="managed-elsewhere" />
            <button type="button" onClick={() => onNavigate('security')} className="font-infinity-body text-[12px] font-medium text-infinity-signal hover:underline">
              Go
            </button>
          </div>
        </div>
      </SettingsCard>

      <ComingSoonSetting icon={Lock} title="Data-sharing controls" description="Controls over analytics or third-party data sharing aren't available yet." />
    </div>
  )
}

// ---------------------------------------------------------------------------------------------
// Billing — real plan/usage data doesn't exist yet; Billing itself is being rebuilt
// ---------------------------------------------------------------------------------------------

function BillingSection() {
  return (
    <SettingsCard>
      <div className="flex items-center gap-2">
        <p className="font-infinity-body text-[13px] font-medium text-infinity-text-primary">Plan, usage & billing status</p>
        <StatusBadge status="managed-elsewhere" />
      </div>
      <p className="mt-1.5 text-[13px] leading-relaxed text-infinity-text-secondary">
        Plan and usage detail is part of TitanIQ's in-progress Billing rebuild — it isn't ready to show here yet.
      </p>
      <Link
        to="/app/billing"
        className="mt-3 inline-flex h-8 items-center justify-center gap-1.5 whitespace-nowrap rounded-infinity-sm border border-infinity-border-default bg-infinity-ground-2 px-3 font-infinity-body text-[12.5px] font-medium text-infinity-text-primary transition-colors duration-100 hover:border-infinity-border-strong"
      >
        <CreditCard className="size-3.5" aria-hidden="true" /> Manage Billing
      </Link>
    </SettingsCard>
  )
}

// ---------------------------------------------------------------------------------------------
// Administration — role-gated, links only
// ---------------------------------------------------------------------------------------------

function AdministrationSection() {
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <StatusBadge status="available" />
        <span className="text-[12px] text-infinity-text-muted">Available to administrators</span>
      </div>
      <SettingsCard className="p-3.5">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2.5">
            <ServerCog className="size-4 shrink-0 text-infinity-text-muted" aria-hidden="true" />
            <div>
              <p className="font-infinity-body text-[13px] font-medium text-infinity-text-primary">Operations Center</p>
              <p className="mt-0.5 text-[12px] text-infinity-text-secondary">Provider health, pipelines, and platform operations.</p>
            </div>
          </div>
          <Link
            to="/app/ops"
            className="inline-flex h-8 shrink-0 items-center justify-center whitespace-nowrap rounded-infinity-sm border border-infinity-border-default bg-infinity-ground-2 px-3 font-infinity-body text-[12.5px] font-medium text-infinity-text-primary transition-colors duration-100 hover:border-infinity-border-strong"
          >
            Open
          </Link>
        </div>
      </SettingsCard>
      <SettingsCard className="p-3.5">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2.5">
            <FlaskConical className="size-4 shrink-0 text-infinity-text-muted" aria-hidden="true" />
            <div>
              <p className="font-infinity-body text-[13px] font-medium text-infinity-text-primary">Prediction Laboratory</p>
              <p className="mt-0.5 text-[12px] text-infinity-text-secondary">Model training, registries, and prediction generation controls.</p>
            </div>
          </div>
          <Link
            to="/app/football/lab"
            className="inline-flex h-8 shrink-0 items-center justify-center whitespace-nowrap rounded-infinity-sm border border-infinity-border-default bg-infinity-ground-2 px-3 font-infinity-body text-[12.5px] font-medium text-infinity-text-primary transition-colors duration-100 hover:border-infinity-border-strong"
          >
            Open
          </Link>
        </div>
      </SettingsCard>
    </div>
  )
}
