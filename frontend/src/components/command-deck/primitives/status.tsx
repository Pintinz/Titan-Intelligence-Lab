/**
 * CDStatusDot — a live system-status indicator (Vercel deployment-status convention: a small
 * dot + label, never a decorative badge). `pulse` drives a real animated ring for the "live"
 * state only — every other state stays still, so pulsing means something.
 */
export function CDStatusDot({
  label,
  tone = 'ready',
}: {
  label: string
  tone: 'ready' | 'live' | 'idle' | 'building'
}) {
  const color =
    tone === 'live' ? 'var(--cd-live)' : tone === 'ready' ? 'var(--cd-accent)' : 'var(--cd-text-muted)'
  const pulse = tone === 'live' || tone === 'building'
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="relative flex size-1.5 shrink-0">
        {pulse && (
          <span
            className="absolute inline-flex size-full animate-ping rounded-full opacity-60 motion-reduce:hidden"
            style={{ backgroundColor: color }}
            aria-hidden="true"
          />
        )}
        <span className="relative inline-flex size-1.5 rounded-full" style={{ backgroundColor: color }} aria-hidden="true" />
      </span>
      <span
        className="font-[var(--cd-font-telemetry)] text-[11px] font-medium uppercase tracking-[0.08em]"
        style={{ color: tone === 'live' ? 'var(--cd-live)' : 'var(--cd-text-secondary)' }}
      >
        {label}
      </span>
    </span>
  )
}
