import type { LucideIcon } from 'lucide-react'
import { Activity, Radar, Timer } from 'lucide-react'
import { CDPanel } from './primitives/panel'
import { CDTelemetryValue } from './primitives/telemetry'

/**
 * AIMatchSnapshot — real system-state telemetry, read before picking a market. Deliberately
 * three cards, not the brief's original longer list ("Momentum", "Tactical Balance", "Upset
 * Probability" etc.) — those aren't real computed values anywhere in the backend for this page,
 * and this session's standing rule is never to fabricate a number to fill a card. Three honest
 * readings beat eight invented ones; market-specific numbers (confidence, probability) live in
 * Generated Intelligence once a market is actually picked, not duplicated up here.
 */
export function AIMatchSnapshot({
  intelligenceTypeCount,
  matchStatusLabel,
  matchStatusTone,
  aiReady,
}: {
  intelligenceTypeCount: number
  matchStatusLabel: string
  matchStatusTone: 'live' | 'idle' | 'accent'
  aiReady: boolean
}) {
  return (
    <div className="grid gap-3 sm:grid-cols-3">
      <SnapshotCard
        icon={Radar}
        label="AI Readiness"
        value={aiReady ? 'Ready' : 'Building'}
        tone={aiReady ? 'accent' : 'idle'}
        detail={aiReady ? 'Trained models are live for this fixture' : 'No trained model has real coverage yet'}
      />
      <SnapshotCard
        icon={Activity}
        label="Intelligence Types"
        value={intelligenceTypeCount}
        tone="default"
        detail={`${intelligenceTypeCount} market${intelligenceTypeCount === 1 ? '' : 's'} available to generate`}
      />
      <SnapshotCard
        icon={Timer}
        label="Match Status"
        value={matchStatusLabel}
        tone={matchStatusTone}
        detail={matchStatusTone === 'live' ? 'In progress right now' : undefined}
      />
    </div>
  )
}

function SnapshotCard({
  icon: Icon,
  label,
  value,
  tone,
  detail,
}: {
  icon: LucideIcon
  label: string
  value: string | number
  tone: 'default' | 'accent' | 'idle' | 'live'
  detail?: string
}) {
  const toneColor =
    tone === 'accent' ? 'var(--cd-accent)' : tone === 'live' ? 'var(--cd-live)' : tone === 'idle' ? 'var(--cd-text-muted)' : 'var(--cd-text-primary)'
  return (
    <CDPanel padding="tight">
      <div className="flex items-start justify-between gap-2">
        <span className="font-[var(--cd-font-telemetry)] text-[11px] font-medium uppercase tracking-[0.08em]" style={{ color: 'var(--cd-text-muted)' }}>
          {label}
        </span>
        <Icon className="size-4 shrink-0" style={{ color: toneColor }} aria-hidden="true" />
      </div>
      <div className="mt-2">
        <CDTelemetryValue value={value} size="md" />
      </div>
      {detail && (
        <p className="mt-1.5 font-[var(--cd-font-body)] text-[11px] leading-snug" style={{ color: 'var(--cd-text-muted)' }}>
          {detail}
        </p>
      )}
    </CDPanel>
  )
}
