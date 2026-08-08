import { CDTelemetryValue } from './primitives/telemetry'

/**
 * CompetitionSnapshot — a compact KPI strip, every value a deterministic count/derivation over
 * the fixtures this page already fetched (no new request). `nextMatch` is a plain "Home vs Away"
 * string, never a prediction value — this page is for discovery, not evidence.
 */
export function CompetitionSnapshot({
  fixtures,
  upcoming,
  completed,
  teams,
  nextMatch,
}: {
  fixtures: number
  upcoming: number
  completed: number
  teams: number
  nextMatch: string | null
}) {
  return (
    <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-5">
      <SnapshotTile label="Fixtures" value={fixtures} />
      <SnapshotTile label="Upcoming" value={upcoming} />
      <SnapshotTile label="Completed" value={completed} />
      <SnapshotTile label="Teams" value={teams} />
      <SnapshotTile label="Next match" text={nextMatch ?? '—'} wide />
    </div>
  )
}

function SnapshotTile({ label, value, text, wide }: { label: string; value?: number; text?: string; wide?: boolean }) {
  return (
    <div
      className={`rounded-[var(--cd-radius-md)] border px-3 py-2.5 text-center ${wide ? 'col-span-2 sm:col-span-1' : ''}`}
      style={{ borderColor: 'var(--cd-border-hairline)', backgroundColor: 'var(--cd-surface-2)' }}
    >
      {text !== undefined ? (
        <p className="truncate font-[var(--cd-font-body)] text-[13px] font-semibold" style={{ color: 'var(--cd-text-primary)' }}>
          {text}
        </p>
      ) : (
        <CDTelemetryValue value={value ?? 0} size="sm" />
      )}
      <p className="mt-0.5 truncate font-[var(--cd-font-telemetry)] text-[9px] font-medium uppercase tracking-[0.06em]" style={{ color: 'var(--cd-text-muted)' }}>
        {label}
      </p>
    </div>
  )
}
