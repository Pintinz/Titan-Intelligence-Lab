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
 * Mission Hero — full-width opening instrument. The search trigger opens the app's one real
 * Command Palette (via `useCommandPaletteStore`, shared with the topbar) rather than building a
 * second search surface. "Generate Intelligence" scrolls to the AI Ready Fixtures section below
 * (an honest anchor — there's no single generic "generate" target without a chosen fixture) while
 * every other quick action deep-links to a real, already-shipped destination.
 */
export function MissionHero({ firstName, status }: { firstName?: string; status: MissionHeroStatus }) {
  const setPaletteOpen = useCommandPaletteStore((s) => s.setOpen)
  const defaultSport = SPORT_SLUGS[0].slug

  return (
    <div
      className="relative overflow-hidden rounded-[var(--cd-radius-2xl)] p-6 sm:p-9"
      style={{ background: 'var(--cd-card-surface)', border: '1px solid var(--cd-card-border)', boxShadow: 'var(--cd-card-shadow)' }}
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
            {firstName ? `Mission Control — welcome back, ${firstName}` : 'Mission Control'}
          </h1>
          <p className="mt-2.5 max-w-xl font-[var(--cd-font-body)] text-[13.5px] leading-relaxed sm:text-[15px]" style={{ color: 'var(--cd-text-secondary)' }}>
            Real-time AI sports intelligence across Football, Basketball, Baseball and Table Tennis.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          <button
            type="button"
            onClick={() => setPaletteOpen(true)}
            aria-label="Search matches, teams, players, competitions"
            className="flex h-11 w-full max-w-sm items-center gap-2.5 rounded-[var(--cd-radius-md)] border px-3.5 backdrop-blur-md transition-all duration-[var(--cd-motion-base)] hover:border-[var(--cd-accent)] hover:shadow-[var(--cd-glow-accent)]"
            style={{ borderColor: 'var(--cd-border-default)', backgroundColor: 'color-mix(in srgb, var(--cd-surface-2) 65%, transparent)', color: 'var(--cd-text-muted)' }}
          >
            <Search className="size-4 shrink-0" aria-hidden="true" />
            <span className="min-w-0 flex-1 truncate text-left font-[var(--cd-font-body)] text-[13px]">Search matches, teams, players, competitions…</span>
            <kbd
              className="hidden shrink-0 rounded border px-1.5 py-0.5 font-[var(--cd-font-tabular)] text-[10px] sm:inline-block"
              style={{ borderColor: 'var(--cd-border-hairline)', color: 'var(--cd-text-muted)' }}
            >
              Ctrl K
            </kbd>
          </button>
        </div>

        <div className="flex flex-wrap gap-2">
          <CDButton variant="secondary" size="sm" href="#ai-ready" icon={<Sparkles className="size-3.5" aria-hidden="true" />}>
            Generate Intelligence
          </CDButton>
          <CDButton variant="secondary" size="sm" href={`/app/${defaultSport}/matches`} icon={<CalendarDays className="size-3.5" aria-hidden="true" />}>
            Browse Matches
          </CDButton>
          <CDButton variant="secondary" size="sm" href={`/app/${defaultSport}/lab`} icon={<FlaskConical className="size-3.5" aria-hidden="true" />}>
            Prediction Laboratory
          </CDButton>
          <CDButton variant="secondary" size="sm" href="/app/graph" icon={<Waypoints className="size-3.5" aria-hidden="true" />}>
            Knowledge Graph
          </CDButton>
          <CDButton variant="secondary" size="sm" href="/app/insights" icon={<LayoutGrid className="size-3.5" aria-hidden="true" />}>
            Open Workspace
          </CDButton>
        </div>

        <div className="flex flex-wrap items-center gap-x-6 gap-y-2 border-t pt-4" style={{ borderColor: 'var(--cd-border-hairline)' }}>
          <StatusItem label="AI Models" statusLabel="Online" tone="ready" />
          <StatusItem label="Prediction Engine" statusLabel={status.predictionEngine.label} tone={status.predictionEngine.tone} />
          <StatusItem label="Live Monitoring" statusLabel={status.liveMonitoring.label} tone={status.liveMonitoring.tone} />
          {status.lastSync && (
            <span className="font-[var(--cd-font-telemetry)] text-[11px]" style={{ color: 'var(--cd-text-muted)' }}>
              Last sync <span className="font-[var(--cd-font-tabular)] tabular-nums">{status.lastSync}</span>
            </span>
          )}
        </div>
      </div>
    </div>
  )
}

function StatusItem({ label, statusLabel, tone }: { label: string; statusLabel: string; tone: SystemStatusTone }) {
  return (
    <div className="flex items-center gap-2">
      <span className="font-[var(--cd-font-body)] text-[11px]" style={{ color: 'var(--cd-text-muted)' }}>
        {label}
      </span>
      <CDStatusDot label={statusLabel} tone={tone === 'ready' ? 'ready' : tone === 'building' ? 'building' : 'idle'} />
    </div>
  )
}
