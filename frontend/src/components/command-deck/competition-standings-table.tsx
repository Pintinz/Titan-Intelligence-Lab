import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { ListOrdered } from 'lucide-react'
import { MissionEmptyState } from './mission-control/mission-section'
import type { StandingRowDto } from '@/lib/api/types'

/** `StandingRowDto.record` is a real `{won, drawn, lost}` bag from the provider — no goals-for/
 * against/differential field exists anywhere on this DTO, so the table never claims one. */
function record(row: StandingRowDto): { won: number; drawn: number; lost: number; played: number } {
  const r = row.record as { won?: number; drawn?: number; lost?: number }
  const won = r.won ?? 0
  const drawn = r.drawn ?? 0
  const lost = r.lost ?? 0
  return { won, drawn, lost, played: won + drawn + lost }
}

/**
 * CompetitionStandingsTable — real fields only: rank, team, W/D/L, played (derived by summing
 * W+D+L, the DTO has no separate field), points. No GF/GA/GD (not in `StandingRowDto`), no
 * qualification-zone highlighting (no backend rule names one).
 */
export function CompetitionStandingsTable({ standings, sportSlug }: { standings: StandingRowDto[]; sportSlug: string }) {
  if (standings.length === 0) {
    return (
      <MissionEmptyState
        icon={ListOrdered}
        title="Standings unavailable"
        description="TitanIQ has not received standings data for this competition yet."
      />
    )
  }

  return (
    <div className="overflow-x-auto rounded-[var(--cd-radius-xl)] border" style={{ borderColor: 'var(--cd-border-default)', backgroundColor: 'var(--cd-surface-1)' }}>
      <table className="w-full font-[var(--cd-font-body)] text-[13px]">
        <thead>
          <tr className="border-b text-left" style={{ borderColor: 'var(--cd-border-hairline)', backgroundColor: 'var(--cd-surface-2)' }}>
            <Th align="left">Pos</Th>
            <Th align="left">Team</Th>
            <Th align="right">P</Th>
            <Th align="right">W</Th>
            <Th align="right">D</Th>
            <Th align="right">L</Th>
            <Th align="right">Pts</Th>
          </tr>
        </thead>
        <tbody>
          {standings.map((row) => {
            const { won, drawn, lost, played } = record(row)
            return (
              <tr key={row.team_id} className="border-t first:border-t-0" style={{ borderColor: 'var(--cd-border-hairline)' }}>
                <td className="px-4 py-2.5 font-[var(--cd-font-tabular)] tabular-nums" style={{ color: 'var(--cd-text-muted)' }}>
                  {row.rank}
                </td>
                <td className="px-4 py-2.5">
                  <Link to={`/app/${sportSlug}/teams/${row.team_id}`} className="font-medium transition-colors" style={{ color: 'var(--cd-text-primary)' }}>
                    {row.team_name}
                  </Link>
                </td>
                <td className="px-4 py-2.5 text-right font-[var(--cd-font-tabular)] tabular-nums" style={{ color: 'var(--cd-text-secondary)' }}>
                  {played}
                </td>
                <td className="px-4 py-2.5 text-right font-[var(--cd-font-tabular)] tabular-nums" style={{ color: 'var(--cd-text-secondary)' }}>
                  {won}
                </td>
                <td className="px-4 py-2.5 text-right font-[var(--cd-font-tabular)] tabular-nums" style={{ color: 'var(--cd-text-secondary)' }}>
                  {drawn}
                </td>
                <td className="px-4 py-2.5 text-right font-[var(--cd-font-tabular)] tabular-nums" style={{ color: 'var(--cd-text-secondary)' }}>
                  {lost}
                </td>
                <td className="px-4 py-2.5 text-right font-[var(--cd-font-tabular)] text-[14px] font-bold tabular-nums" style={{ color: 'var(--cd-text-primary)' }}>
                  {row.points}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function Th({ children, align }: { children: ReactNode; align: 'left' | 'right' }) {
  return (
    <th
      className={`px-4 py-2.5 font-[var(--cd-font-telemetry)] text-[10.5px] font-medium uppercase tracking-[0.06em] ${align === 'right' ? 'text-right' : 'text-left'}`}
      style={{ color: 'var(--cd-text-muted)' }}
    >
      {children}
    </th>
  )
}
