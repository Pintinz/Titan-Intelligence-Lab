interface AuthFormHeaderProps {
  title: string
  subtitle: string
}

export function AuthFormHeader({ title, subtitle }: AuthFormHeaderProps) {
  return (
    <div className="space-y-2 text-center animate-card-entrance" style={{ animationDelay: '50ms' }}>
      <div className="flex items-center justify-center gap-2 mb-4">
        <span className="inline-block size-2 rounded-full bg-accent-primary animate-pulse" aria-hidden="true" />
        <span className="text-xs font-telemetry uppercase tracking-wider text-accent-primary">TitanIQ</span>
      </div>
      <h1 className="font-display text-2xl font-semibold text-text-primary">{title}</h1>
      <p className="text-sm text-text-secondary">{subtitle}</p>
    </div>
  )
}
