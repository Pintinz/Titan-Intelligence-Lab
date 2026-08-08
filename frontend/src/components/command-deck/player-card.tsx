import { Link } from 'react-router-dom'
import { Sparkles, ChevronRight } from 'lucide-react'
import { CDButton } from './primitives/button'
import { CDStatusDot } from './primitives/status'
import { CD_DOMAIN_COLOR_VAR, type DomainKey } from './primitives/domain'
import type { EnrichedPlayer } from '@/lib/hooks/use-player-intelligence'

/**
 * PlayerCard — Player Intelligence's card unit, same flat-bordered/Vercel-grammar shape as
 * `TeamCard`. The backend exposes no player headshot, so the avatar tile shows the player's real
 * team crest (joined via `team_id`) instead of a stock silhouette or fabricated photo; players
 * with no team fall back to an initial like an unlogo'd team does. "Generate Intelligence" only
 * renders when the player's team has a real next fixture — there is no player-level generate
 * endpoint, so this deep-links to the team's actual next scheduled fixture, same honesty rule as
 * `TeamCard`'s own CTA.
 */
export function PlayerCard({
  player,
  sportSlug,
  sportDomain,
  aiReady,
}: {
  player: EnrichedPlayer
  sportSlug: string
  sportDomain: Extract<DomainKey, 'football' | 'basketball' | 'baseball' | 'table-tennis'>
  aiReady: boolean
}) {
  const domainColor = CD_DOMAIN_COLOR_VAR[sportDomain]
  const generateHref = aiReady && player.teamNextFixtureId ? `/app/${sportSlug}/matches/${player.teamNextFixtureId}` : null
  const playerHref = `/app/${sportSlug}/players/${player.id}`

  return (
    <div
      className="group relative flex flex-col gap-4 overflow-hidden rounded-[var(--cd-radius-md)] transition-colors duration-[var(--cd-motion-base)] ease-out hover:-translate-y-px"
      style={{ padding: '1.125rem', backgroundColor: 'var(--cd-surface-1)', border: '1px solid var(--cd-border-default)' }}
      onMouseEnter={(e) => {
        e.currentTarget.style.borderColor = domainColor
        e.currentTarget.style.backgroundColor = 'var(--cd-surface-2)'
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.borderColor = 'var(--cd-border-default)'
        e.currentTarget.style.backgroundColor = 'var(--cd-surface-1)'
      }}
    >
      <Link to={playerHref} aria-label={player.name} className="absolute inset-0 z-0" />
      <span
        className="pointer-events-none absolute inset-x-0 top-0 h-[2px] origin-left scale-x-0 transition-transform duration-[var(--cd-motion-base)] ease-out group-hover:scale-x-100"
        style={{ backgroundColor: domainColor }}
        aria-hidden="true"
      />

      <div className="pointer-events-none relative z-10 flex items-start gap-3">
        <span
          className="flex shrink-0 items-center justify-center overflow-hidden rounded-[var(--cd-radius-sm)] border"
          style={{ width: 40, height: 40, borderColor: 'var(--cd-border-default)', backgroundColor: 'var(--cd-surface-3)' }}
        >
          {player.teamLogoUrl ? (
            <img src={player.teamLogoUrl} alt="" className="object-contain" style={{ width: 26, height: 26 }} loading="lazy" />
          ) : (
            <span aria-hidden="true" className="font-[var(--cd-font-display)] text-[13px] font-semibold" style={{ color: domainColor }}>
              {player.name.charAt(0).toUpperCase()}
            </span>
          )}
        </span>
        <div className="min-w-0">
          <p className="truncate font-[var(--cd-font-display)] text-[14.5px] font-semibold" style={{ color: 'var(--cd-text-primary)' }}>
            {player.name}
          </p>
          {player.position && (
            <p className="mt-0.5 truncate font-[var(--cd-font-telemetry)] text-[10.5px] uppercase tracking-[0.06em]" style={{ color: domainColor }}>
              {player.position}
            </p>
          )}
          {player.team_name ? (
            player.team_id ? (
              <Link
                to={`/app/${sportSlug}/teams/${player.team_id}`}
                className="pointer-events-auto relative z-10 mt-0.5 block truncate font-[var(--cd-font-body)] text-[11.5px] hover:underline"
                style={{ color: 'var(--cd-text-muted)' }}
              >
                {player.team_name}
              </Link>
            ) : (
              <p className="mt-0.5 truncate font-[var(--cd-font-body)] text-[11.5px]" style={{ color: 'var(--cd-text-muted)' }}>
                {player.team_name}
              </p>
            )
          ) : (
            <p className="mt-0.5 font-[var(--cd-font-body)] text-[11.5px]" style={{ color: 'var(--cd-text-muted)' }}>
              Unassigned
            </p>
          )}
        </div>
      </div>

      <div
        className="pointer-events-none relative z-10 mt-auto flex items-center justify-between gap-2 border-t pt-3.5"
        style={{ borderColor: 'var(--cd-border-hairline)' }}
      >
        {player.teamLiveNow ? (
          <CDStatusDot label="Team live now" tone="live" />
        ) : (
          <span className="font-[var(--cd-font-telemetry)] text-[10px] uppercase tracking-[0.05em]" style={{ color: 'var(--cd-text-muted)' }}>
            {player.date_of_birth ? new Date(player.date_of_birth).getFullYear() : ' '}
          </span>
        )}
        <div className="flex items-center gap-2">
          {generateHref ? (
            <CDButton variant="secondary" size="sm" href={generateHref} icon={<Sparkles className="size-3" aria-hidden="true" />} className="pointer-events-auto">
              Team Intelligence
            </CDButton>
          ) : player.team_id ? (
            <Link
              to={`/app/${sportSlug}/teams/${player.team_id}`}
              className="group/link pointer-events-auto inline-flex items-center gap-0.5 font-[var(--cd-font-body)] text-[11px] font-medium transition-colors"
              style={{ color: 'var(--cd-text-secondary)' }}
            >
              View Team <ChevronRight className="size-3 transition-transform duration-[var(--cd-motion-base)] group-hover/link:translate-x-0.5" aria-hidden="true" />
            </Link>
          ) : null}
        </div>
      </div>
    </div>
  )
}
