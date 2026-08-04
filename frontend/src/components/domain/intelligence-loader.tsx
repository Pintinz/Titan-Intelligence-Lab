import { cn } from '@/lib/cn'

interface IntelligenceLoaderProps {
  message?: string
  size?: 'sm' | 'md' | 'lg'
  className?: string
}

const loaderMessages = [
  'Analyzing recent form...',
  'Evaluating confidence factors...',
  'Updating Knowledge Graph...',
  'Calculating predictions...',
  'Processing news impact...',
  'Preparing explanation...',
  'Syncing community signals...',
  'Recalibrating models...',
]

export function IntelligenceLoader({ message, size = 'md', className }: IntelligenceLoaderProps) {
  const displayMessage = message || loaderMessages[Math.floor(Math.random() * loaderMessages.length)]

  return (
    <div className={cn('flex flex-col items-center gap-4', className)}>
      {/* Animated confidence telemetry-style loader */}
      <div className="flex items-center gap-1">
        {[0, 1, 2, 3].map((i) => (
          <div
            key={i}
            className={cn(
              'rounded-[1px] bg-accent-primary transition-opacity duration-300',
              size === 'sm' && 'h-2 w-1',
              size === 'md' && 'h-3 w-1.5',
              size === 'lg' && 'h-4 w-2',
            )}
            style={{
              opacity: 0.3 + (i * 0.2),
              animation: `confidence-pulse 1.2s ease-in-out infinite`,
              animationDelay: `${i * 0.15}s`,
            }}
          />
        ))}
      </div>

      {/* Brand message */}
      <p className={cn(
        'font-telemetry text-center tracking-wide text-accent-primary',
        size === 'sm' && 'text-xs',
        size === 'md' && 'text-sm',
        size === 'lg' && 'text-base',
      )}>
        {displayMessage}
      </p>
    </div>
  )
}
