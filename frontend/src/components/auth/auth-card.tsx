import type { ReactNode } from 'react'
import { cn } from '@/lib/cn'

interface AuthCardProps {
  children: ReactNode
  className?: string
}

export function AuthCard({ children, className }: AuthCardProps) {
  return (
    <div className={cn(
      'w-full max-w-sm space-y-6 animate-card-entrance',
      className
    )}>
      {/* Glassmorphic background layers for premium feel */}
      <div className="absolute inset-0 -z-10 rounded-2xl bg-gradient-to-br from-bg-secondary/40 to-bg-elevated/20 blur-xl" />

      <div className={cn(
        'relative border border-border-default/30 backdrop-blur-md',
        'bg-bg-secondary/40 rounded-2xl p-8',
        'shadow-elevation-2 transition-all duration-300',
        'hover:border-border-default/50'
      )}>
        {children}
      </div>
    </div>
  )
}
