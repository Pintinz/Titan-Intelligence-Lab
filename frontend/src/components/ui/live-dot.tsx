export function LiveDot() {
  return (
    <span className="relative inline-flex size-1.5">
      <span className="absolute inline-flex size-full animate-ping rounded-full bg-live opacity-60 motion-reduce:animate-none" />
      <span className="relative inline-flex size-1.5 rounded-full bg-live" />
    </span>
  )
}
