import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import { AiNetworkIllustration } from '@/components/illustrations/ai-network-illustration'
import { transitionSlow } from '@/lib/motion'

/**
 * Shared split-screen chrome for the auth pages (login/signup/forgot-password/reset-password) —
 * left panel is branding/motion only, right panel renders each page's own form untouched (every
 * supabase.auth.* call site, zod schema, and useForm hook stays exactly as it was). Below the
 * `lg` breakpoint the left panel collapses so the form remains the only content on mobile.
 */
export function AuthSplitLayout({ eyebrow, title, tagline, children }: { eyebrow: string; title: string; tagline: string; children: ReactNode }) {
  return (
    <main className="flex min-h-svh">
      <div
        className="relative hidden w-1/2 flex-col justify-between overflow-hidden p-12 lg:flex"
        style={{ backgroundImage: 'var(--gradient-mesh-hero)' }}
      >
        <AiNetworkIllustration className="pointer-events-none absolute inset-0 h-full w-full opacity-40" />

        <Link to="/" className="relative font-display text-lg font-semibold text-text-primary">
          TitanIQ
        </Link>

        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={transitionSlow}
          className="relative max-w-md rounded-xl border border-border-glass bg-bg-glass p-6 backdrop-blur-[var(--blur-glass-md)]"
        >
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-text-muted">{eyebrow}</p>
          <h2 className="mt-3 font-display text-3xl font-semibold text-text-primary">{title}</h2>
          <p className="mt-3 text-text-secondary">{tagline}</p>
        </motion.div>

        <p className="relative text-xs text-text-muted">
          Calibrated, explainable sports intelligence — Football, Basketball, Baseball, Table Tennis.
        </p>
      </div>

      <div className="flex flex-1 items-center justify-center bg-bg-primary px-6 py-16">
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={transitionSlow}
          className="w-full max-w-sm rounded-lg border border-border-default bg-bg-elevated p-8 shadow-[var(--shadow-elevation-3)]"
        >
          {children}
        </motion.div>
      </div>
    </main>
  )
}
