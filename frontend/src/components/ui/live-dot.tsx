export function LiveDot() {
  return (
    <span className="relative inline-flex size-1.5">
      <span className="absolute inline-flex size-full animate-live-indicator rounded-full bg-live opacity-60" />
      <span className="relative inline-flex size-1.5 rounded-full bg-live shadow-[0_0_0_1px_var(--color-live)] animate-live-indicator" />
    </span>
  )
}
