import { useEffect, useId, useState } from 'react'
import { Link } from 'react-router-dom'
import { confidenceTier, type ConfidenceTier } from '@/components/domain/confidence-telemetry'
import { LiveDot } from '@/components/ui/live-dot'
import { humanizeFactorKey, type TeamRef } from '@/components/infinity/evidence-explorer'
import { predictionValueLabel } from '@/lib/predictions/value-label'
import { SPORT_SLUGS } from '@/lib/hooks/use-sport'
import { cn } from '@/lib/cn'
import type { PublicFeaturedIntelligenceDto } from '@/lib/api/types'

/**
 * TitanIQ's "miniature intelligence report" — the visual language the front page uses to present
 * a prediction, at two densities (hero "Today's Top Forecast" panel / compact grid card). Renders
 * ONLY real fields from `PublicFeaturedIntelligenceDto` — no fabricated per-factor percentages,
 * model provenance, or expected-goals figures, since `public_router.py`'s featured-intelligence
 * endpoint doesn't return them. What's real: the model's probability for the predicted outcome,
 * its calibrated confidence, the market, the fixture's kickoff, up to a few real SHAP-derived
 * evidence factors (direction only), and the timestamp the inference actually ran.
 *
 * `probability_distribution` carries the model's real calibrated distribution when the market has
 * one (every HOME_DRAW_AWAY-kind market — Match Winner, First/Second Half Winner, etc. — keyed
 * `HOME_WIN`/`DRAW`/`AWAY_WIN`); the hero renders that as a real three-way Home/Draw/Away
 * breakdown. For markets with no such shape (BTTS, Over/Under, ...) — or an older prediction row
 * from before this field existed, where the dict is empty — `ProbabilityBand` falls back to the
 * honest two-way split (this outcome vs. everything else, a mathematical certainty from the one
 * real `probability` number) rather than inventing a three-way curve that isn't there. There's
 * also no model-provenance field (algorithm/champion status) on this endpoint, so the card never
 * claims one — it shows the real market name instead of a guessed or hardcoded "Champion" badge.
 */

const SPACE_GROTESK = '"Space Grotesk", "Inter", system-ui, sans-serif'
const STALE_THRESHOLD_HOURS = 12

const TIER_LABEL: Record<ConfidenceTier, string> = {
  peak: 'ELITE',
  high: 'HIGH',
  medium: 'MODERATE',
  low: 'LOW',
}

function tierTextClass(tier: ConfidenceTier) {
  if (tier === 'peak' || tier === 'high') return 'text-[var(--li-positive)]'
  if (tier === 'medium') return 'text-[var(--li-blue)]'
  return 'text-[var(--li-text-muted)]'
}

function tierBarClass(tier: ConfidenceTier) {
  if (tier === 'peak' || tier === 'high') return 'bg-[var(--li-positive)]'
  if (tier === 'medium') return 'bg-[var(--li-blue)]'
  return 'bg-[var(--li-text-muted)]'
}

function tierPillClass(tier: ConfidenceTier) {
  if (tier === 'peak' || tier === 'high')
    return 'border-[var(--li-positive)]/30 bg-[var(--li-positive-muted)] text-[var(--li-positive)]'
  if (tier === 'medium') return 'border-[var(--li-blue)]/30 bg-[var(--li-blue-muted)] text-[var(--li-blue)]'
  return 'border-[var(--li-border-strong)] bg-[var(--li-surface-elevated)] text-[var(--li-text-muted)]'
}

function formatKickoffShort(iso: string) {
  const date = new Date(iso)
  const today = new Date()
  const isToday = date.toDateString() === today.toDateString()
  const time = date.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })
  return isToday ? `Today · ${time}` : `${date.toLocaleDateString(undefined, { weekday: 'short' })} · ${time}`
}

function hoursSince(iso: string | null): number | null {
  if (!iso) return null
  return (Date.now() - new Date(iso).getTime()) / 3_600_000
}

function formatLastComputedRelative(iso: string | null): string {
  const hours = hoursSince(iso)
  if (hours === null) return '—'
  const mins = Math.round(hours * 60)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins} min ago`
  if (hours < 24) return `${Math.round(hours)}h ago`
  return `${Math.round(hours / 24)}d ago`
}

function formatLastComputedAbsolute(iso: string | null): string | null {
  if (!iso) return null
  return new Date(iso).toLocaleString(undefined, { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })
}

/** Restrained ease-out count-up — respects `prefers-reduced-motion` by jumping straight to the
 * real value instead of animating. Never fabricates the number, just its arrival. */
function useCountUp(target: number, durationMs = 700): number {
  const [value, setValue] = useState(0)
  useEffect(() => {
    if (typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      setValue(target)
      return
    }
    let start: number | null = null
    let raf: number
    function tick(ts: number) {
      if (start === null) start = ts
      const progress = Math.min(1, (ts - (start ?? ts)) / durationMs)
      setValue(Math.round(target * (1 - Math.pow(1 - progress, 3))))
      if (progress < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [target, durationMs])
  return value
}

export function TeamCrest({
  team,
  size = 'md',
}: {
  team: TeamRef
  /** 'md' (44px) is the compact-card size; 'lg' (68px) is for the hero, which has enough
   * vertical headroom around the crest row to absorb a bigger mark without growing the card. */
  size?: 'md' | 'lg'
}) {
  return (
    // Always centered, never edge-aligned: the crest must sit in the horizontal middle of its own
    // team name regardless of how each name's truncated width compares to the crest's fixed size —
    // edge-aligning them (as this used to via an `align` prop) visibly drifts the crest off-center
    // whenever the name is narrower or wider than the crest.
    <div className="flex min-w-0 flex-1 flex-col items-center gap-2">
      <span
        className={cn(
          'relative flex shrink-0 items-center justify-center overflow-hidden rounded-full border border-[var(--li-border)] bg-[var(--li-surface-elevated)]',
          size === 'lg' ? 'size-17' : 'size-11',
        )}
      >
        {team.logoUrl ? (
          <img src={team.logoUrl} alt="" className="size-full object-contain p-1.5" loading="lazy" />
        ) : (
          <span className={cn('font-semibold text-[var(--li-text-secondary)]', size === 'lg' && 'text-xl')} aria-hidden="true">
            {team.name.charAt(0).toUpperCase()}
          </span>
        )}
      </span>
      <p className="max-w-[9.5rem] truncate text-center text-sm sm:max-w-[11rem]" style={{ fontFamily: SPACE_GROTESK, fontWeight: 600, color: 'var(--li-text-primary)' }}>
        {team.name}
      </p>
    </div>
  )
}

export function CalibratedConfidencePill({ confidence }: { confidence: number }) {
  const tier = confidenceTier(confidence)
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full border px-2.5 py-1 font-mono text-[11px] font-semibold uppercase tracking-wider',
        tierPillClass(tier),
      )}
    >
      {TIER_LABEL[tier]}
    </span>
  )
}

export function IntelligenceCardSkeleton() {
  return (
    <div className="animate-pulse space-y-4">
      <div className="h-3 w-28 rounded bg-[var(--li-border)]" />
      <div className="h-11 w-full rounded bg-[var(--li-border)]" />
      <div className="h-16 rounded-[var(--li-radius-md)] bg-[var(--li-border)]" />
      <div className="h-24 rounded-[var(--li-radius-md)] bg-[var(--li-border)]" />
    </div>
  )
}

export function EngineIdleState() {
  return (
    <div className="flex flex-1 flex-col items-center justify-center py-10 text-center">
      <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-[var(--li-text-muted)]">
        Intelligence Engine
      </span>
      <p className="mt-3 text-base font-semibold text-[var(--li-text-primary)]">Awaiting published intelligence</p>
      <p className="mt-2 max-w-xs text-sm text-[var(--li-text-secondary)]">
        A prediction publishes only once it clears its confidence threshold — nothing ships without
        evidence behind it.
      </p>
    </div>
  )
}

/** The honest "distribution" visual: a smooth band split at the one real probability this
 * endpoint provides. The curve's shape is presentational (no per-outcome data exists to justify a
 * literal multi-modal density), but the split position and both percentages are exactly the real
 * `probability` field and its complement — never a fabricated Home/Draw/Away breakdown. */
function ProbabilityBand({ predictedPct, predictedLabel }: { predictedPct: number; predictedLabel: string }) {
  const rawId = useId().replace(/[:]/g, '')
  const width = 300
  const height = 64
  const baselineY = 52
  const peakY = 12
  const splitX = Math.max(2, Math.min(width - 2, (predictedPct / 100) * width))
  const curvePath = `M0,${baselineY} C ${width * 0.22},${baselineY} ${width * 0.32},${peakY} ${width * 0.5},${peakY} C ${width * 0.68},${peakY} ${width * 0.78},${baselineY} ${width},${baselineY} L ${width},${height} L 0,${height} Z`

  return (
    <div className="mt-6">
      <svg viewBox={`0 0 ${width} ${height}`} className="h-14 w-full" preserveAspectRatio="none" aria-hidden="true">
        <defs>
          <clipPath id={`${rawId}-left`}>
            <rect x="0" y="0" width={splitX} height={height} />
          </clipPath>
          <clipPath id={`${rawId}-right`}>
            <rect x={splitX} y="0" width={width - splitX} height={height} />
          </clipPath>
        </defs>
        <path d={curvePath} fill="var(--li-cyan-muted)" clipPath={`url(#${rawId}-left)`} />
        <path d={curvePath} fill="var(--li-surface-elevated)" clipPath={`url(#${rawId}-right)`} />
        <line x1="0" y1={baselineY} x2={width} y2={baselineY} stroke="var(--li-border)" strokeWidth="1" />
        <line x1={splitX} y1={height} x2={splitX} y2={peakY - 3} stroke="var(--li-cyan)" strokeWidth="1.5" />
        <circle cx={splitX} cy={peakY - 3} r="3.5" fill="var(--li-cyan)" style={{ filter: 'drop-shadow(0 0 5px var(--li-cyan-strong))' }} />
      </svg>
      <div className="mt-2 flex items-center justify-between gap-2 text-[11px]">
        <span className="min-w-0 truncate font-medium text-[var(--li-cyan)]">
          {predictedLabel} · {predictedPct}%
        </span>
        <span className="shrink-0 text-[var(--li-text-muted)]">Other outcomes · {100 - predictedPct}%</span>
      </div>
    </div>
  )
}

/** The real three-way visual, shown only when `probability_distribution` actually carries all
 * three `HOME_WIN`/`DRAW`/`AWAY_WIN` keys — every number here is the model's own calibrated
 * distribution, never derived or invented. Whichever outcome leads gets the larger, brand-colored
 * treatment; the other two stay small and muted, so the visual hierarchy always matches reality. */
function HomeDrawAwayBreakdown({
  homeLabel,
  awayLabel,
  homePct,
  drawPct,
  awayPct,
}: {
  homeLabel: string
  awayLabel: string
  homePct: number
  drawPct: number
  awayPct: number
}) {
  const entries = [
    { key: 'home', label: homeLabel, pct: homePct },
    { key: 'draw', label: 'Draw', pct: drawPct },
    { key: 'away', label: awayLabel, pct: awayPct },
  ]
  const leaderPct = Math.max(homePct, drawPct, awayPct)

  return (
    <div className="mt-3 grid grid-cols-3 gap-2">
      {entries.map((e) => {
        const isLeading = e.pct === leaderPct
        return (
          <div key={e.key} className="flex min-w-0 flex-col items-center gap-1 text-center">
            <p
              className={cn('font-bold tabular-nums', isLeading ? 'text-3xl text-[var(--li-cyan)]' : 'text-lg text-[var(--li-text-muted)]')}
              style={{ fontFamily: SPACE_GROTESK }}
            >
              {e.pct}%
            </p>
            <p
              className={cn(
                'max-w-full truncate text-[11px] font-medium uppercase tracking-wide',
                isLeading ? 'text-[var(--li-cyan)]' : 'text-[var(--li-text-muted)]',
              )}
            >
              {e.label}
            </p>
          </div>
        )
      })}
    </div>
  )
}

function FooterStat({
  label,
  value,
  sub,
  stale,
  bar,
}: {
  label: string
  value: string
  sub?: string
  stale?: boolean
  bar?: React.ReactNode
}) {
  return (
    <div className="min-w-0 px-3 text-center first:pl-0 last:pr-0">
      <p className="font-sans text-[10px] font-semibold uppercase tracking-[0.1em] text-[var(--li-text-muted)]">{label}</p>
      <p
        className={cn('mt-1 flex items-center justify-center gap-1.5 text-sm leading-tight font-semibold text-balance', stale ? 'text-[var(--li-warning)]' : 'text-[var(--li-text-primary)]')}
        style={{ fontFamily: SPACE_GROTESK }}
      >
        {stale && <span className="mt-0.5 size-1.5 shrink-0 self-start rounded-full bg-[var(--li-warning)]" aria-hidden="true" />}
        <span className="min-w-0">{value}</span>
      </p>
      {sub && <p className="mt-0.5 truncate font-mono text-[10px] text-[var(--li-text-muted)]">{sub}</p>}
      {bar}
    </div>
  )
}

/** "Today's Top Forecast" — the front page's centerpiece: a forecast, not a betting slip. The
 * predicted outcome is dominant; confidence, market, and freshness are honest supporting facts,
 * never a claimed "Champion" model badge this endpoint can't back. Staggered entrance (~700ms,
 * `prefers-reduced-motion`-aware) — never a continuous/looping animation. */
export function HeroIntelligenceReport({ pick }: { pick: PublicFeaturedIntelligenceDto }) {
  const isLive = pick.status === 'live'
  const probabilityPct = useCountUp(Math.round(pick.probability * 100))
  const confidencePct = useCountUp(Math.round(pick.confidence_composite * 100))
  const valueLabel = predictionValueLabel(pick.value, pick.home_team ?? undefined, pick.away_team ?? undefined)
  const supporting = pick.evidence_highlights.supporting
  const homeTeam: TeamRef = { name: pick.home_team?.name ?? 'TBD', logoUrl: pick.home_team?.logo_url }
  const awayTeam: TeamRef = { name: pick.away_team?.name ?? 'TBD', logoUrl: pick.away_team?.logo_url }
  const tier = confidenceTier(pick.confidence_composite)
  const staleHours = hoursSince(pick.generated_at)
  const isStale = staleHours !== null && staleHours >= STALE_THRESHOLD_HOURS
  const lastComputedAbsolute = formatLastComputedAbsolute(pick.generated_at)
  const sportSlug = SPORT_SLUGS.find((s) => s.code === pick.sport_code)?.slug ?? pick.sport_code
  const distribution = pick.probability_distribution
  const hasHomeDrawAway =
    distribution.HOME_WIN !== undefined && distribution.DRAW !== undefined && distribution.AWAY_WIN !== undefined

  return (
    <div>
      <div className="flex items-center justify-between gap-2">
        <span className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--li-blue)] motion-safe:animate-[li-rise_var(--motion-duration-slow,420ms)_ease-out]">
          Today's Top Forecast
        </span>
        <Link
          to="/signup"
          className="shrink-0 text-[11px] font-medium text-[var(--li-cyan)] hover:text-[var(--li-cyan-hover)] motion-safe:animate-[li-rise_var(--motion-duration-slow,420ms)_ease-out]"
        >
          View all →
        </Link>
      </div>

      <div
        className="mt-3 flex items-center justify-between gap-2 motion-safe:animate-[li-rise_var(--motion-duration-slow,420ms)_ease-out]"
        style={{ animationDelay: '40ms', animationFillMode: 'backwards' }}
      >
        <span className="truncate text-xs text-[var(--li-text-secondary)]">{pick.competition_name ?? pick.sport_code}</span>
        {isLive ? (
          <span className="inline-flex shrink-0 items-center gap-1.5 text-[11px] font-medium text-[var(--li-risk)]">
            <LiveDot /> Live
          </span>
        ) : (
          <span className="shrink-0 font-mono text-xs text-[var(--li-text-muted)]">{formatKickoffShort(pick.scheduled_at)}</span>
        )}
      </div>

      <div
        // Same grid-cols-3 as HomeDrawAwayBreakdown below, deliberately — a flex row here and a
        // grid row there give each side its own, different column math (flex-1 vs. equal thirds),
        // so the crest/name landed in a different horizontal spot than its own percentage below
        // it. Sharing one column template keeps every column's center identical between rows.
        className="mt-5 grid grid-cols-3 items-center gap-2 motion-safe:animate-[li-rise_var(--motion-duration-slow,420ms)_ease-out]"
        style={{ animationDelay: '90ms', animationFillMode: 'backwards' }}
      >
        <TeamCrest team={homeTeam} size="lg" />
        <div className="flex justify-center">
          <span className="shrink-0 rounded-full border border-[var(--li-border)] bg-[var(--li-surface)] px-2.5 py-1 font-mono text-[10px] font-medium text-[var(--li-text-muted)]">
            VS
          </span>
        </div>
        <TeamCrest team={awayTeam} size="lg" />
      </div>

      {hasHomeDrawAway ? (
        <div
          className="motion-safe:animate-[li-rise_var(--motion-duration-slow,420ms)_ease-out]"
          style={{ animationDelay: '150ms', animationFillMode: 'backwards' }}
        >
          <HomeDrawAwayBreakdown
            homeLabel={homeTeam.name}
            awayLabel={awayTeam.name}
            homePct={Math.round(distribution.HOME_WIN * 100)}
            drawPct={Math.round(distribution.DRAW * 100)}
            awayPct={Math.round(distribution.AWAY_WIN * 100)}
          />
        </div>
      ) : (
        <>
          <div
            className="mt-6 text-center motion-safe:animate-[li-rise_var(--motion-duration-slow,420ms)_ease-out]"
            style={{ animationDelay: '150ms', animationFillMode: 'backwards' }}
          >
            <p className="text-5xl font-bold tabular-nums text-[var(--li-cyan)]" style={{ fontFamily: SPACE_GROTESK }}>
              {probabilityPct}%
            </p>
            <p className="mt-1 text-sm font-semibold uppercase tracking-wide text-[var(--li-cyan)]" style={{ fontFamily: SPACE_GROTESK }}>
              {valueLabel}
            </p>
          </div>

          <div
            className="motion-safe:animate-[li-rise_var(--motion-duration-slow,420ms)_ease-out]"
            style={{ animationDelay: '220ms', animationFillMode: 'backwards' }}
          >
            <ProbabilityBand predictedPct={probabilityPct} predictedLabel={valueLabel} />
          </div>
        </>
      )}

      {supporting.length > 0 && (
        <p
          className="mt-4 text-center text-[12px] leading-relaxed text-[var(--li-text-muted)] motion-safe:animate-[li-rise_var(--motion-duration-slow,420ms)_ease-out]"
          style={{ animationDelay: '260ms', animationFillMode: 'backwards' }}
        >
          Backed by {supporting.slice(0, 2).map(humanizeFactorKey).join(', ').toLowerCase()}
          {'. '}
          <Link to={`/app/${sportSlug}/matches/${pick.fixture_id}`} className="font-medium text-[var(--li-cyan)] hover:text-[var(--li-cyan-hover)]">
            View full explanation →
          </Link>
        </p>
      )}

      <div
        className="mt-6 grid grid-cols-3 divide-x divide-[var(--li-border)] border-t border-[var(--li-border)] pt-4 motion-safe:animate-[li-rise_var(--motion-duration-slow,420ms)_ease-out]"
        style={{ animationDelay: '300ms', animationFillMode: 'backwards' }}
      >
        <FooterStat
          label="Confidence"
          value={`${confidencePct}%`}
          bar={
            <div className="mx-auto mt-2 h-1 w-14 overflow-hidden rounded-full bg-[var(--li-border)]">
              <div className={cn('h-full rounded-full transition-[width]', tierBarClass(tier))} style={{ width: `${confidencePct}%` }} />
            </div>
          }
        />
        <FooterStat label="Market" value={pick.market_name} />
        <FooterStat label="Updated" value={formatLastComputedRelative(pick.generated_at)} sub={lastComputedAbsolute ?? undefined} stale={isStale} />
      </div>
    </div>
  )
}

/** Compact grid-card density — Featured Predictions. Same honest-fields discipline as the hero. */
export function CompactIntelligenceReport({ pick }: { pick: PublicFeaturedIntelligenceDto }) {
  const isLive = pick.status === 'live'
  const probabilityPct = Math.round(pick.probability * 100)
  const valueLabel = predictionValueLabel(pick.value, pick.home_team ?? undefined, pick.away_team ?? undefined)
  const tier = confidenceTier(pick.confidence_composite)
  const homeTeam: TeamRef = { name: pick.home_team?.short_name ?? pick.home_team?.name ?? 'TBD', logoUrl: pick.home_team?.logo_url }
  const awayTeam: TeamRef = { name: pick.away_team?.short_name ?? pick.away_team?.name ?? 'TBD', logoUrl: pick.away_team?.logo_url }

  return (
    <>
      <div className="flex items-center justify-between gap-2">
        <span className="truncate text-[11px] font-semibold uppercase tracking-wider text-[var(--li-blue)]">
          {pick.competition_name ?? pick.sport_code}
        </span>
        {isLive ? (
          <span className="inline-flex shrink-0 items-center gap-1.5 text-[11px] font-medium text-[var(--li-risk)]">
            <LiveDot /> Live
          </span>
        ) : (
          <span className="shrink-0 font-mono text-[10px] text-[var(--li-text-muted)]">{formatKickoffShort(pick.scheduled_at)}</span>
        )}
      </div>

      <div className="mt-4 flex items-center justify-center gap-3">
        <TeamCrest team={homeTeam} />
        <div className="shrink-0 text-center">
          <p className="text-2xl font-bold tabular-nums text-[var(--li-cyan)]" style={{ fontFamily: SPACE_GROTESK }}>
            {probabilityPct}%
          </p>
        </div>
        <TeamCrest team={awayTeam} />
      </div>
      <p className="mt-1 text-center text-xs font-semibold uppercase tracking-wide text-[var(--li-cyan)]" style={{ fontFamily: SPACE_GROTESK }}>
        {valueLabel}
      </p>

      <div className="mt-4 grid grid-cols-3 gap-2 border-t border-[var(--li-border)] pt-3 text-center">
        <div>
          <p className="font-sans text-[9px] font-semibold uppercase tracking-wider text-[var(--li-text-muted)]">Confidence</p>
          <p className={cn('mt-1 font-mono text-[11px] font-semibold uppercase', tierTextClass(tier))}>{TIER_LABEL[tier]}</p>
        </div>
        <div className="min-w-0">
          <p className="font-sans text-[9px] font-semibold uppercase tracking-wider text-[var(--li-text-muted)]">Market</p>
          <p className="mt-1 truncate font-mono text-[11px] font-medium text-[var(--li-text-primary)]">{pick.market_name}</p>
        </div>
        <div>
          <p className="font-sans text-[9px] font-semibold uppercase tracking-wider text-[var(--li-text-muted)]">Kickoff</p>
          <p className="mt-1 truncate font-mono text-[11px] font-medium text-[var(--li-text-primary)]">
            {isLive ? 'Now' : formatKickoffShort(pick.scheduled_at)}
          </p>
        </div>
      </div>
    </>
  )
}

