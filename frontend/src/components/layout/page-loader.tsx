import { Loader2 } from 'lucide-react'

export function PageLoader() {
  return (
    <div className="flex h-full min-h-[50vh] items-center justify-center text-text-muted">
      <Loader2 className="h-5 w-5 animate-spin" aria-label="Loading" />
    </div>
  )
}
