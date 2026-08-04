import type { ReactNode } from 'react'
import type { LucideIcon } from 'lucide-react'
import { Link } from 'react-router-dom'
import { CircleSlash2 } from 'lucide-react'
import {
  ResponsiveContainer,
  LineChart,
  Line,
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  type TooltipContentProps,
} from 'recharts'
import { cn } from '@/lib/cn'
import { Card } from '@/components/ui/card'

/** Consistent header for every Operations Center page — eyebrow / title / description / actions. */
export function OpsPageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow: string
  title: string
  description?: string
  actions?: ReactNode
}) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div>
        <p className="font-telemetry text-xs font-semibold uppercase tracking-[0.16em] text-accent-primary">
          {eyebrow}
        </p>
        <h2 className="mt-1 font-display text-lg font-semibold text-text-primary">{title}</h2>
        {description && <p className="mt-1 max-w-2xl text-sm text-text-secondary">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  )
}

/** A compact metric tile — the atomic unit of every telemetry-dense ops screen. Optionally links
 * through to the page that can explain the number (the "drill-down" the brief asks for). */
export function MetricTile({
  icon: Icon,
  label,
  value,
  tone = 'default',
  href,
  hint,
}: {
  icon: LucideIcon
  label: string
  value: ReactNode
  tone?: 'default' | 'live' | 'success' | 'warning' | 'danger'
  href?: string
  hint?: string
}) {
  const toneColor = {
    default: 'text-accent-primary',
    live: 'text-live',
    success: 'text-success',
    warning: 'text-warning',
    danger: 'text-danger',
  }[tone]

  const content = (
    <Card className={cn('p-4 transition-all duration-200', href && 'hover:border-border-strong hover:shadow-elevation-2')}>
      <div className="flex items-center justify-between">
        <p className="text-xs text-text-muted">{label}</p>
        <Icon className={cn('size-3.5', toneColor)} aria-hidden="true" />
      </div>
      <div className="mt-2 font-telemetry text-xl font-medium tabular-nums text-text-primary">{value}</div>
      {hint && <p className="mt-1 truncate text-[11px] text-text-muted">{hint}</p>}
    </Card>
  )

  return href ? <Link to={href}>{content}</Link> : content
}

/** Wraps a chart or list in a titled card — the standard content container for ops sections. */
export function SectionCard({
  icon: Icon,
  title,
  description,
  actions,
  children,
}: {
  icon?: LucideIcon
  title: string
  description?: string
  actions?: ReactNode
  children: ReactNode
}) {
  return (
    <Card className="p-5">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-2">
          {Icon && <Icon className="mt-0.5 size-4 shrink-0 text-accent-primary" aria-hidden="true" />}
          <div>
            <p className="font-display text-sm font-semibold text-text-primary">{title}</p>
            {description && <p className="mt-0.5 text-xs text-text-secondary">{description}</p>}
          </div>
        </div>
        {actions}
      </div>
      {children}
    </Card>
  )
}

/**
 * Distinct from `EmptyState` on purpose: `EmptyState` means "the endpoint works, there's just no
 * data yet." This means "no endpoint exists yet" — a materially different, honest signal per the
 * brief's own "Backend Pending... without fake data" instruction. Names the exact endpoint that
 * would need to exist so the gap reads as a scoped, known TODO rather than an abandoned page.
 */
export function BackendPendingState({
  title,
  description,
  recommendedEndpoint,
}: {
  title: string
  description: string
  recommendedEndpoint?: string
}) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed border-border-default px-6 py-12 text-center">
      <div className="flex size-10 items-center justify-center rounded-full bg-bg-secondary">
        <CircleSlash2 className="size-4 text-text-muted" aria-hidden="true" />
      </div>
      <div className="space-y-1.5">
        <p className="font-display text-sm font-semibold text-text-primary">{title}</p>
        <p className="max-w-md text-sm text-text-secondary">{description}</p>
      </div>
      {recommendedEndpoint && (
        <code className="rounded-md bg-bg-secondary px-2.5 py-1 font-mono text-[11px] text-text-muted">
          Recommended: {recommendedEndpoint}
        </code>
      )}
    </div>
  )
}

function ChartTooltip({ active, payload, label }: TooltipContentProps) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-md border border-border-default bg-bg-elevated px-3 py-2 shadow-elevation-2">
      {label !== undefined && <p className="font-mono text-[11px] text-text-muted">{String(label)}</p>}
      {payload.map((p) => (
        <p key={String(p.dataKey)} className="font-telemetry text-xs text-text-primary">
          {p.name}: <span className="tabular-nums">{typeof p.value === 'number' ? p.value.toFixed(2) : String(p.value)}</span>
        </p>
      ))}
    </div>
  )
}

const AXIS_PROPS = {
  stroke: 'var(--color-text-muted)',
  tick: { fill: 'var(--color-text-muted)', fontSize: 11 },
  tickLine: false,
  axisLine: { stroke: 'var(--color-border-subtle)' },
}

/** F1-telemetry-style line chart — confidence/latency/accuracy over time. One accent line by
 * default; pass `series` for multiple. */
export function TelemetryLineChart({
  data,
  dataKey,
  xKey = 'x',
  color = 'var(--color-accent-primary)',
  height = 220,
  series,
}: {
  data: Array<Record<string, unknown>>
  dataKey?: string
  xKey?: string
  color?: string
  height?: number
  series?: Array<{ key: string; color: string; name?: string }>
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
        <CartesianGrid stroke="var(--color-border-subtle)" strokeDasharray="3 3" vertical={false} />
        <XAxis dataKey={xKey} {...AXIS_PROPS} />
        <YAxis {...AXIS_PROPS} width={40} />
        <Tooltip content={ChartTooltip} cursor={{ stroke: 'var(--color-border-default)' }} />
        {series
          ? series.map((s) => (
              <Line
                key={s.key}
                type="monotone"
                dataKey={s.key}
                name={s.name ?? s.key}
                stroke={s.color}
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 3 }}
              />
            ))
          : (
            <Line
              type="monotone"
              dataKey={dataKey ?? 'y'}
              stroke={color}
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 3 }}
            />
          )}
      </LineChart>
    </ResponsiveContainer>
  )
}

/** Area chart for volume-shaped metrics (requests, predictions generated, articles ingested). */
export function TelemetryAreaChart({
  data,
  dataKey,
  xKey = 'x',
  color = 'var(--color-accent-primary)',
  height = 220,
}: {
  data: Array<Record<string, unknown>>
  dataKey: string
  xKey?: string
  color?: string
  height?: number
}) {
  const gradientId = `ops-area-${dataKey}`
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity={0.35} />
            <stop offset="100%" stopColor={color} stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke="var(--color-border-subtle)" strokeDasharray="3 3" vertical={false} />
        <XAxis dataKey={xKey} {...AXIS_PROPS} />
        <YAxis {...AXIS_PROPS} width={40} />
        <Tooltip content={ChartTooltip} cursor={{ stroke: 'var(--color-border-default)' }} />
        <Area type="monotone" dataKey={dataKey} stroke={color} strokeWidth={2} fill={`url(#${gradientId})`} />
      </AreaChart>
    </ResponsiveContainer>
  )
}

/** Bar chart — distributions (confidence buckets, market coverage counts). */
export function TelemetryBarChart({
  data,
  dataKey,
  xKey = 'x',
  color = 'var(--color-accent-primary)',
  height = 220,
}: {
  data: Array<Record<string, unknown>>
  dataKey: string
  xKey?: string
  color?: string
  height?: number
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
        <CartesianGrid stroke="var(--color-border-subtle)" strokeDasharray="3 3" vertical={false} />
        <XAxis dataKey={xKey} {...AXIS_PROPS} />
        <YAxis {...AXIS_PROPS} width={40} />
        <Tooltip content={ChartTooltip} cursor={{ fill: 'var(--color-bg-secondary)' }} />
        <Bar dataKey={dataKey} fill={color} radius={[3, 3, 0, 0]} maxBarSize={28} />
      </BarChart>
    </ResponsiveContainer>
  )
}

/** Small inline health pill — Healthy / Warning / Offline, the vocabulary the brief specifies. */
export function HealthPill({ status }: { status: 'healthy' | 'warning' | 'offline' | 'unknown' }) {
  const config = {
    healthy: { label: 'Healthy', className: 'bg-success-muted text-success' },
    warning: { label: 'Warning', className: 'bg-warning-muted text-warning' },
    offline: { label: 'Offline', className: 'bg-danger-muted text-danger' },
    unknown: { label: 'Unknown', className: 'bg-bg-secondary text-text-muted' },
  }[status]
  return (
    <span className={cn('inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide', config.className)}>
      {config.label}
    </span>
  )
}
