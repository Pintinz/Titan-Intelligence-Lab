import type { ReactNode } from 'react'
import { IntelligenceCanvas } from './intelligence-canvas'
import { cn } from '@/lib/cn'

interface AuthLayoutProps {
  children: ReactNode
}

export function AuthLayout({ children }: AuthLayoutProps) {
  return (
    <div className="flex min-h-svh bg-bg-primary">
      {/* Left: Intelligence Canvas - 60% desktop, 55% tablet, hidden mobile */}
      <div className="hidden md:flex w-full md:w-3/5 lg:w-3/5 xl:w-3/5">
        <IntelligenceCanvas />
      </div>

      {/* Right: Auth Card - 40% desktop, 45% tablet, full-width mobile */}
      <div className={cn(
        'w-full md:w-2/5 lg:w-2/5 xl:w-2/5',
        'flex items-center justify-center px-6 py-8 md:px-8 lg:px-12'
      )}>
        {children}
      </div>
    </div>
  )
}
