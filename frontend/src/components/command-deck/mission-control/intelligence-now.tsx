import { Compass, CircleCheck, TriangleAlert, ShieldAlert, Radio, CalendarDays, Sparkles, Rss } from 'lucide-react'
import { humanizeFactorKey, type TeamRef } from '@/components/infinity/evidence-explorer'
import { predictionValueLabel } from '@/lib/predictions/value-label'
import { SPORT_SLUGS } from '@/lib/hooks/use-sport'
import type { RankedIntelligenceItem } from '@/lib/hooks/use-priority-intelligence'
import { CDButton } from '../primitives/button'
import { CDLabel } from '../primitives/panel'
import { CDConfidenceGauge } from '../primitives/gauge'
import { MissionSection, MissionEmptyState } from './mission-section'

function sportSlugFor(code: string): string {
  return SPORT_SLUGS.find((s) => s.code === code)?.slug ?? code
}

function confidenceTierLabel(pct: number): string {
  if (pct >= 95) return 'Elite'
  if (pct >= 85) return 'High'
  if (pct >= 75) return 'Strong'
  return 'Moderate'
}

export interface IntelligenceSnapshotStats {
  live: number | null
  today: number | null
  aiReady: number | null
  contextUpdates: number | null
}

/**
 * Intelligence Now — the page's dominant surface, replacing the old "seven equal metrics" opener.
 * Left: the single #1-ranked pick (same pool `/app/picks` uses), presented with real "why this
 * matters" evidence rather than a generic AI claim — the collapsed `ai_explanation` narration
 * already free on the bulk pick, plus real SHAP-backed top features and real per-team injury
 * status (never an invented severity tier — `InjuryDto` has no such field, so this shows the
 * provider's own `status` string). Right: a compact 4-cell snapshot, not four giant KPI tiles.
 */
export function IntelligenceNow({
  item,
  isLoading,
  snapshot,
}: {
  item: RankedIntelligenceItem | undefined
  isLoading: boolean
  snapshot: IntelligenceSnapshotStats
}) {
  return (
    <MissionSection
      id="intelligence-now"
      title="Intelligence Now"
      subtitle="TitanIQ's strongest signal right now, with the evidence behind it"
      icon={<Compass className="size-4" aria-hidden="true" />}
      domain="predictions"
    >
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_272px]">
        {isLoading && (
          <div className="h-[380px] animate-pulse rounded-[var(--cd-radius-2xl)] motion-reduce:animate-none" style={{ background: 'var(--cd-card-surface)', border: '1px solid var(--cd-card-border)' }} />
        )}
        {!isLoading && !item && (
          <MissionEmptyState
            icon={Compass}
            title="No qualifying intelligence has been published yet."
            description="Intelligence Now surfaces the strongest currently available signal as soon as TitanIQ publishes a prediction with at least moderate confidence."
          />
        )}
        {!isLoading && item && <PrioritySignalCard item={item} />}

        <IntelligenceSnapshotPanel stats={snapshot} />
      </div>
    </MissionSection>
  )
}

function PrioritySignalCard({ item }: { item: RankedIntelligenceItem }) {
  const { pick, fixture } = item
  const homeTeam: TeamRef = { name: fixture.home_team.name, logoUrl: fixture.home_team.logo_url }
  const awayTeam: TeamRef = { name: fixture.away_team.name, logoUrl: fixture.away_team.logo_url }
  const confidencePct = Math.round(pick.confidence_composite * 100)
  const probabilityPct = Math.round(pick.probability * 100)
  const href = `/app/${sportSlugFor(pick.sport_code)}/matches/${fixture.id}`
  const injuries = [...item.homeInjuries.map((i) => ({ ...i, teamName: fixture.home_team.name })), ...item.awayInjuries.map((i) => ({ ...i, teamName: fixture.away_team.name }))]

  return (
    <div
      className="relative overflow-hidden rounded-[var(--cd-radius-2xl)] p-6 backdrop-blur-md"
      style={{ background: 'var(--cd-card-surface)', border: '1px solid var(--cd-accent-strong)', boxShadow: 'var(--cd-elevation-accent), var(--cd-card-shadow)' }}
    >
      <div
        className="pointer-events-none absolute -top-16 -right-16 h-64 w-64 rounded-full opacity-50"
        style={{ background: 'radial-gradient(circle, var(--cd-accent-muted) 0%, transparent 70%)' }}
        aria-hidden="true"
      />
      <div className="relative flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5">
          <Sparkles className="size-3.5" style={{ color: 'var(--cd-accent)' }} aria-hidden="true" />
          <CDLabel tone="accent">Priority Signal</CDLabel>
        </div>
        <span className="font-[var(--cd-font-telemetry)] text-[10px] font-medium uppercase tracking-[0.06em]" style={{ color: 'var(--cd-text-muted)' }}>
          {fixture.competition_name}
        </span>
      </div>

      <div className="relative mt-4 flex items-center justify-center gap-4">
        <TeamCrest team={homeTeam} />
        <span className="font-[var(--cd-font-body)] text-[13px]" style={{ color: 'var(--cd-text-muted)' }}>vs</span>
        <TeamCrest team={awayTeam} />
      </div>

      <div className="relative mt-5 flex flex-wrap items-center justify-between gap-4">
        <div className="min-w-0">
          <p className="font-[var(--cd-font-display)] text-[11px] font-medium" style={{ color: 'var(--cd-text-muted)' }}>{pick.market_name}</p>
          <p className="mt-1 truncate font-[var(--cd-font-display)] text-[26px] font-bold leading-tight" style={{ color: 'var(--cd-text-primary)' }}>
            {predictionValueLabel(pick.value, homeTeam, awayTeam)}
          </p>
          <p className="mt-1.5 font-[var(--cd-font-body)] text-[12px]" style={{ color: 'var(--cd-text-secondary)' }}>
            <span className="font-[var(--cd-font-tabular)] font-semibold tabular-nums" style={{ color: 'var(--cd-text-primary)' }}>{probabilityPct}%</span> probability
          </p>
        </div>
        <CDConfidenceGauge value={pick.confidence_composite} size={92} label={confidenceTierLabel(confidencePct)} />
      </div>

      {pick.ai_explanation && (
        <div className="relative mt-5 border-t pt-4" style={{ borderColor: 'var(--cd-border-hairline)' }}>
          <CDLabel>Why this matters</CDLabel>
          <p className="mt-1.5 font-[var(--cd-font-body)] text-[13px] leading-relaxed" style={{ color: 'var(--cd-text-secondary)' }}>{pick.ai_explanation}</p>
        </div>
      )}

      {(item.topPositiveFeatures.length > 0 || item.topNegativeFeatures.length > 0) && (
        <ul className="relative mt-3.5 space-y-1.5">
          {item.topPositiveFeatures.slice(0, 3).map(([key]) => (
            <li key={key} className="flex items-start gap-1.5">
              <CircleCheck className="mt-0.5 size-3.5 shrink-0" style={{ color: 'var(--cd-positive)' }} aria-hidden="true" />
              <span className="font-[var(--cd-font-body)] text-[12.5px]" style={{ color: 'var(--cd-text-secondary)' }}>{humanizeFactorKey(key)}</span>
            </li>
          ))}
          {item.topNegativeFeatures.slice(0, 2).map(([key]) => (
            <li key={key} className="flex items-start gap-1.5">
              <TriangleAlert className="mt-0.5 size-3.5 shrink-0" style={{ color: 'var(--cd-negative)' }} aria-hidden="true" />
              <span className="font-[var(--cd-font-body)] text-[12.5px]" style={{ color: 'var(--cd-text-secondary)' }}>{humanizeFactorKey(key)}</span>
            </li>
          ))}
        </ul>
      )}

      <div className="relative mt-4 flex items-start gap-1.5 border-t pt-3.5" style={{ borderColor: 'var(--cd-border-hairline)' }}>
        <ShieldAlert className="mt-0.5 size-3.5 shrink-0" style={{ color: injuries.length > 0 ? 'var(--cd-negative)' : 'var(--cd-text-muted)' }} aria-hidden="true" />
        <div className="min-w-0">
          <CDLabel>Context</CDLabel>
          {injuries.length > 0 ? (
            <p className="mt-0.5 font-[var(--cd-font-body)] text-[12.5px] leading-relaxed" style={{ color: 'var(--cd-text-secondary)' }}>
              {injuries.slice(0, 2).map((inj) => `${inj.player_name ?? 'A player'} (${inj.teamName}) — ${inj.status}`).join('; ')}
            </p>
          ) : (
            <p className="mt-0.5 font-[var(--cd-font-body)] text-[12.5px]" style={{ color: 'var(--cd-text-muted)' }}>No verified lineup issue currently affecting this prediction.</p>
          )}
        </div>
      </div>

      <CDButton variant="primary" size="md" href={href} className="relative mt-5 w-full justify-center">
        View Match Intelligence
      </CDButton>
    </div>
  )
}

function TeamCrest({ team }: { team: TeamRef }) {
  return (
    <div className="flex flex-1 flex-col items-center gap-1.5 min-w-0">
      <span className="relative flex size-14 shrink-0 items-center justify-center">
        <span className="pointer-events-none absolute inset-[-6px] rounded-full opacity-70" style={{ background: 'radial-gradient(circle, var(--cd-accent-muted) 0%, transparent 72%)' }} aria-hidden="true" />
        {team.logoUrl ? (
          <img src={team.logoUrl} alt="" className="relative size-14 shrink-0 object-contain" loading="lazy" />
        ) : (
          <span aria-hidden="true" className="relative flex size-14 shrink-0 items-center justify-center rounded-full font-[var(--cd-font-display)] text-[17px] font-semibold" style={{ backgroundColor: 'var(--cd-surface-3)', color: 'var(--cd-text-muted)' }}>
            {team.name.charAt(0).toUpperCase()}
          </span>
        )}
      </span>
      <p className="max-w-[8rem] truncate font-[var(--cd-font-body)] text-[13px] font-medium" style={{ color: 'var(--cd-text-primary)' }}>{team.name}</p>
    </div>
  )
}

function IntelligenceSnapshotPanel({ stats }: { stats: IntelligenceSnapshotStats }) {
  const cells: Array<{ label: string; value: number | null; icon: typeof Radio; empty: string; href: string }> = [
    { label: 'Live now', value: stats.live, icon: Radio, empty: 'None live', href: '#live' },
    { label: "Today's fixtures", value: stats.today, icon: CalendarDays, empty: 'Nothing today', href: '#ai-ready' },
    { label: 'AI ready', value: stats.aiReady, icon: Sparkles, empty: 'None ready', href: '#ai-ready' },
    { label: 'Context updates', value: stats.contextUpdates, icon: Rss, empty: 'Quiet', href: '#intelligence-feed' },
  ]
  return (
    <div className="grid grid-cols-2 gap-3 content-start">
      {cells.map((cell) => (
        <a
          key={cell.label}
          href={cell.href}
          className="group flex flex-col gap-2 rounded-[var(--cd-radius-xl)] p-3.5 backdrop-blur-md transition-all duration-[var(--cd-motion-base)] hover:-translate-y-0.5 hover:shadow-[var(--cd-card-shadow-hover)]"
          style={{ background: 'var(--cd-card-surface)', border: '1px solid var(--cd-card-border)', boxShadow: 'var(--cd-card-shadow)' }}
        >
          <cell.icon className="size-3.5" style={{ color: 'var(--cd-text-muted)' }} aria-hidden="true" />
          {cell.value === null ? (
            <span className="inline-block h-6 w-8 animate-pulse rounded" style={{ backgroundColor: 'var(--cd-surface-3)' }} />
          ) : (
            <span className="font-[var(--cd-font-tabular)] text-[22px] font-semibold leading-none tabular-nums" style={{ color: 'var(--cd-text-primary)' }}>
              {cell.value > 0 ? cell.value : '—'}
            </span>
          )}
          <span className="font-[var(--cd-font-telemetry)] text-[9.5px] uppercase tracking-[0.06em]" style={{ color: 'var(--cd-text-muted)' }}>
            {cell.value === 0 ? cell.empty : cell.label}
          </span>
        </a>
      ))}
    </div>
  )
}
