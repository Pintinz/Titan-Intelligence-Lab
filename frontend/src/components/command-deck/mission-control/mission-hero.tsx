import { Link } from 'react-router-dom'
import { Search, Sparkles, CalendarDays, FlaskConical, Waypoints, LayoutGrid } from 'lucide-react'
import { useCommandPaletteStore } from '@/stores/command-palette-store'
import { CDStatusDot } from '../primitives/status'
import { CDButton } from '../primitives/button'
import { SPORT_SLUGS } from '@/lib/hooks/use-sport'

export type SystemStatusTone = 'ready' | 'building' | 'idle'

export interface MissionHeroStatus {
  predictionEngine: { label: string; tone: SystemStatusTone }
  liveMonitoring: { label: string; tone: SystemStatusTone }
  lastSync: string | null
}

/**
 * Mission Hero — the authenticated home's opening instrument, not a marketing hero and not a
 * second navigation surface (global nav already covers that). The search trigger opens the app's
 * one real Command Palette (via `useCommandPaletteStore`, shared with the topbar) rather than
 * building a second search surface. "Generate Intelligence" scrolls to the AI Ready Fixtures
 * section below (an honest anchor — there's no single generic "generate" target without a chosen
 * fixture) while every other quick action deep-links to a real, already-shipped destination.
 * Prediction Laboratory — an admin tool — only renders for `isAdmin`; the array of quick actions
 * itself omits it for everyone else rather than disabling or graying it out.
 */
export function MissionHero({
  greeting,
  name,
  isAdmin,
  status,
}: {
  greeting: string
  name: string | null
  isAdmin: boolean
  status: MissionHeroStatus
}) {
  const setPaletteOpen = useCommandPaletteStore((s) => s.setOpen)
  const defaultSport = SPORT_SLUGS[0].slug

  const secondaryActions = [
    { label: 'Browse Matches', href: '/app/matches', icon: CalendarDays },
    ...(isAdmin ? [{ label: 'Prediction Laboratory', href: `/app/${defaultSport}/lab`, icon: FlaskConical }] : []),
    { label: 'Knowledge Graph', href: '/app/graph', icon: Waypoints },
    { label: 'Open Workspace', href: '/app/insights', icon: LayoutGrid },
  ]

  return (
    <div
      className="relative overflow-hidden rounded-[var(--cd-radius-2xl)] border border-[var(--cd-glass-3-border)] bg-[var(--cd-glass-3-bg)] p-6 backdrop-blur-[var(--cd-glass-3-blur)] sm:p-9"
      style={{ boxShadow: 'var(--cd-card-shadow-hover)' }}
    >
      <div
        className="animate-hero-glow motion-reduce:animate-none pointer-events-none absolute -left-[10%] -top-[30%] h-[420px] w-[420px] rounded-full opacity-70"
        style={{ background: 'radial-gradient(circle, var(--cd-accent-muted) 0%, transparent 70%)' }}
        aria-hidden="true"
      />
      <div
        className="animate-hero-glow motion-reduce:animate-none pointer-events-none absolute -right-[6%] -top-[10%] h-[320px] w-[320px] rounded-full opacity-50"
        style={{ background: 'radial-gradient(circle, var(--cd-accent-muted) 0%, transparent 70%)', animationDelay: '3s' }}
        aria-hidden="true"
      />

      <div className="relative flex flex-col gap-6">
        <div>
          <h1
            className="font-[var(--cd-font-display)] text-[28px] font-semibold leading-tight tracking-[-0.015em] sm:text-[34px]"
            style={{ color: 'var(--cd-text-primary)' }}
          >
            {name ? `${greeting}, ${name}` : greeting}
          </h1>
          <p className="mt-2.5 font-[var(--cd-font-body)] text-[13.5px] leading-relaxed sm:text-[15px]" style={{ color: 'var(--cd-text-secondary)' }}>
            Your intelligence desk is ready.
          </p>
        </div>

        <button
          type="button"
          onClick={() => setPaletteOpen(true)}
          aria-label="Search matches, teams, players, competitions"
          className="flex h-12 w-full max-w-lg items-center gap-2.5 rounded-[var(--cd-radius-lg)] border px-4 backdrop-blur-md transition-all duration-[var(--cd-motion-base)] hover:border-[var(--cd-accent)] hover:shadow-[var(--cd-glow-accent)]"
          style={{ borderColor: 'var(--cd-border-default)', backgroundColor: 'color-mix(in srgb, var(--cd-surface-2) 65%, transparent)', color: 'var(--cd-text-muted)' }}
        >
          <Search className="size-4 shrink-0" aria-hidden="true" />
          <span className="min-w-0 flex-1 truncate text-left font-[var(--cd-font-body)] text-[13.5px]">Search matches, teams, players, competitions…</span>
          <kbd
            className="hidden shrink-0 rounded border px-1.5 py-0.5 font-[var(--cd-font-tabular)] text-[10px] sm:inline-block"
            style={{ borderColor: 'var(--cd-border-hairline)', color: 'var(--cd-text-muted)' }}
          >
            Ctrl K
          </kbd>
        </button>

        <div className="flex flex-col gap-3">
          <CDButton variant="primary" size="md" href="#ai-ready" icon={<Sparkles className="size-4" aria-hidden="true" />} className="w-fit">
            Generate Intelligence
          </CDButton>
          <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
            {secondaryActions.map((action) => (
              <Link
                key={action.label}
                to={action.href}
                className="group inline-flex items-center gap-1.5 font-[var(--cd-font-body)] text-[13px] font-medium transition-colors"
                style={{ color: 'var(--cd-text-secondary)' }}
              >
                <action.icon className="size-3.5 shrink-0 transition-colors group-hover:text-[var(--cd-accent)]" style={{ color: 'var(--cd-text-muted)' }} aria-hidden="true" />
                <span className="group-hover:text-[var(--cd-accent)]">{action.label}</span>
              </Link>
            ))}
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 border-t pt-4" style={{ borderColor: 'var(--cd-border-hairline)' }}>
          <CombinedStatus predictionEngine={status.predictionEngine} liveMonitoring={status.liveMonitoring} />
          {status.lastSync && (
            <span className="font-[var(--cd-font-telemetry)] text-[11px]" style={{ color: 'var(--cd-text-muted)' }}>
              · Updated <span className="font-[var(--cd-font-tabular)] tabular-nums">{status.lastSync}</span>
            </span>
          )}
        </div>
      </div>
    </div>
  )
}

/** One combined status line, not a row of infrastructure tiles — the common case ("everything's
 * fine") stays a single quiet dot; a real degradation on either the prediction engine or live
 * monitoring is the only thing that earns a named warning. */
function CombinedStatus({
  predictionEngine,
  liveMonitoring,
}: {
  predictionEngine: { label: string; tone: SystemStatusTone }
  liveMonitoring: { label: string; tone: SystemStatusTone }
}) {
  if (predictionEngine.tone === 'idle') return <CDStatusDot label="Prediction engine unavailable" tone="idle" />
  if (liveMonitoring.tone === 'idle') return <CDStatusDot label="Live monitoring offline" tone="idle" />
  if (predictionEngine.tone === 'building' || liveMonitoring.tone === 'building') return <CDStatusDot label="Intelligence connecting" tone="building" />
  return <CDStatusDot label="Intelligence online" tone="ready" />
}
