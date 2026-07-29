export function PageLoader() {
  return (
    <div className="flex min-h-[50vh] items-center justify-center">
      <div
        className="size-6 animate-spin rounded-full border-2 border-border-default border-t-accent-primary motion-reduce:animate-none"
        role="status"
        aria-label="Loading"
      />
    </div>
  )
}
