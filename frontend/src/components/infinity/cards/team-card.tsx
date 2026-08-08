import type { CSSProperties } from 'react'
import { ArrowUpRight } from 'lucide-react'
import { useCrestAccentColor } from '@/lib/hooks/use-crest-accent-color'
import { DOMAIN_COLOR_VAR, type DomainKey } from '../primitives/badge'
import { InfinityFollowButton } from '../primitives/follow-button'

export interface TeamCardProps {
  name: string
  domain: 'football' | 'basketball' | 'baseball' | 'table-tennis'
  /** Real fields — populated from `TeamSummaryDto`. */
  country?: string | null
  venueName?: string | null
  logoUrl?: string | null
  /** Demo-only fields for the component showcase — no backend tracks league position or
   * win/draw/loss streaks yet, so real callers must omit these rather than fabricate them. */
  competition?: string
  position?: number
  form?: Array<'W' | 'D' | 'L'>
  /** Omit both to render without a follow toggle (e.g. the design showcase). */
  following?: boolean
  onToggleFollow?: () => void
}

const FORM_COLOR: Record<'W' | 'D' | 'L', string> = {
  W: 'var(--infinity-success)',
  D: 'var(--infinity-text-muted)',
  L: 'var(--infinity-danger)',
}

/** A quieter card language than the broadcast corner-tick panel every other Infinity surface
 * uses — a roster is a directory to scan, not evidence to inspect, so this borrows Vercel's own
 * grammar instead: a hairline border that does all the framing, a flat ground with no glow at
 * rest, a crest held in its own bordered tile rather than floating loose. The one deliberate
 * color touch — the top rule, the crest tile's glow, the hover halo — is never a hardcoded
 * domain color; it's sampled from the team's own real crest artwork (the same technique the Team
 * Hero uses), so every club in the grid reads as visually distinct on genuinely derived data,
 * never an invented palette. */
export function InfinityTeamCard({
  name,
  domain,
  country,
  venueName,
  logoUrl,
  competition,
  position,
  form,
  following,
  onToggleFollow,
}: TeamCardProps) {
  const fallbackTone = DOMAIN_COLOR_VAR[domain as DomainKey]
  const tone = useCrestAccentColor(logoUrl, fallbackTone)
  const subtitle = [country, venueName].filter(Boolean).join(' · ')

  const hoverBorder = `color-mix(in srgb, ${tone} 45%, var(--infinity-border-hairline))`
  const hoverShadow = `0 20px 40px -20px color-mix(in srgb, ${tone} 55%, transparent)`

  return (
    <div
      className="group relative overflow-hidden rounded-infinity-lg border bg-infinity-ground-1 p-4 transition-all duration-200 ease-out hover:-translate-y-0.5"
      style={{ boxShadow: 'var(--team-card-shadow, none)', borderColor: 'var(--team-card-border, var(--infinity-border-hairline))' } as CSSProperties}
      onMouseEnter={(e) => {
        e.currentTarget.style.setProperty('--team-card-shadow', hoverShadow)
        e.currentTarget.style.setProperty('--team-card-border', hoverBorder)
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.removeProperty('--team-card-shadow')
        e.currentTarget.style.removeProperty('--team-card-border')
      }}
    >
      <span
        aria-hidden="true"
        className="absolute inset-x-0 top-0 h-[2px] opacity-70 transition-opacity duration-200 group-hover:opacity-100"
        style={{ background: `linear-gradient(90deg, ${tone}, transparent)` }}
      />

      <div className="flex items-start justify-between gap-2">
        <TeamCrestTile name={name} logoUrl={logoUrl} tone={tone} />
        <div className="flex shrink-0 items-center gap-1.5">
          <ArrowUpRight
            className="size-3.5 -translate-x-0.5 translate-y-0.5 text-infinity-text-muted opacity-0 transition-all duration-150 group-hover:translate-x-0 group-hover:translate-y-0 group-hover:opacity-100"
            aria-hidden="true"
          />
          {onToggleFollow && <InfinityFollowButton following={!!following} onToggle={onToggleFollow} label={name} />}
        </div>
      </div>

      <div className="mt-4 min-w-0">
        <p className="line-clamp-2 font-infinity-display text-[16px] font-semibold leading-snug text-infinity-text-primary">{name}</p>
        {subtitle && <p className="mt-1.5 truncate font-infinity-mono text-[11px] text-infinity-text-muted">{subtitle}</p>}
      </div>

      {(competition || position !== undefined) && (
        <div className="mt-3.5 flex items-center justify-between border-t border-infinity-border-hairline pt-3">
          {competition ? (
            <span className="truncate font-infinity-mono text-[10px] uppercase tracking-[0.06em] text-infinity-text-muted">
              {competition}
            </span>
          ) : (
            <span />
          )}
          {position !== undefined && (
            <span className="shrink-0 font-infinity-telemetry text-[12px] tabular-nums text-infinity-text-secondary">
              #{position}
            </span>
          )}
        </div>
      )}

      {form && form.length > 0 && (
        <div className="mt-3.5 flex gap-1">
          {form.map((result, i) => (
            <span
              key={i}
              className="flex size-[18px] items-center justify-center rounded-[4px] font-infinity-mono text-[9px] font-semibold text-infinity-ground-0"
              style={{ backgroundColor: FORM_COLOR[result] }}
            >
              {result}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

function TeamCrestTile({ name, logoUrl, tone }: { name: string; logoUrl?: string | null; tone: string }) {
  const glow = `radial-gradient(circle at 30% 25%, color-mix(in srgb, ${tone} 30%, transparent), transparent 70%)`
  return (
    <span
      className="relative flex size-14 shrink-0 items-center justify-center overflow-hidden rounded-infinity-md border border-infinity-border-hairline bg-infinity-ground-2 p-2.5 transition-colors duration-200"
      style={{ borderColor: 'var(--team-card-border, var(--infinity-border-hairline))' } as CSSProperties}
    >
      <span
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 opacity-0 transition-opacity duration-200 group-hover:opacity-100"
        style={{ background: glow }}
      />
      {logoUrl ? (
        <img src={logoUrl} alt="" className="relative size-full object-contain drop-shadow-sm" loading="lazy" />
      ) : (
        <span aria-hidden="true" className="relative font-infinity-display text-[17px] font-semibold text-infinity-text-muted">
          {name.charAt(0).toUpperCase()}
        </span>
      )}
    </span>
  )
}
