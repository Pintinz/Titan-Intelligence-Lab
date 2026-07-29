import { useState } from 'react'
import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { Link } from 'react-router-dom'
import { supabase } from '@/lib/supabase'
import { forgotPasswordSchema, type ForgotPasswordValues } from '@/lib/validation/auth-schemas'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { toast } from '@/stores/toast-store'
import { AuthLayout } from '@/components/auth/auth-layout'
import { AuthCard } from '@/components/auth/auth-card'
import { AuthFormHeader } from '@/components/auth/auth-form-header'
import { cn } from '@/lib/cn'

export default function ForgotPasswordPage() {
  const [sent, setSent] = useState(false)
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<ForgotPasswordValues>({ resolver: zodResolver(forgotPasswordSchema) })

  async function onSubmit(values: ForgotPasswordValues) {
    const { error } = await supabase.auth.resetPasswordForEmail(values.email, {
      redirectTo: `${window.location.origin}/reset-password`,
    })

    if (error) {
      toast.danger('Could not send reset link', error.message)
      return
    }

    setSent(true)
    toast.success('Password reset link sent')
  }

  if (sent) {
    return (
      <AuthLayout>
        <AuthCard>
          <div className="space-y-6 text-center animate-card-entrance">
            <div className="space-y-2">
              <div className="mx-auto flex size-12 items-center justify-center rounded-lg bg-success-muted animate-card-entrance" style={{ animationDelay: '50ms' }}>
                <span className="text-lg font-semibold">✓</span>
              </div>
              <h1 className="font-display text-xl font-semibold text-text-primary animate-card-entrance" style={{ animationDelay: '100ms' }}>
                Check your email
              </h1>
              <p className="text-sm text-text-secondary animate-card-entrance" style={{ animationDelay: '150ms' }}>
                We sent a password reset link to your email. Click the link to reset your password.
              </p>
            </div>
            <Link
              to="/login"
              className="inline-block text-sm text-accent-primary hover:text-accent-primary-hover font-medium transition-colors animate-card-entrance"
              style={{ animationDelay: '200ms' }}
            >
              Back to sign in
            </Link>
          </div>
        </AuthCard>
      </AuthLayout>
    )
  }

  return (
    <AuthLayout>
      <AuthCard>
        <AuthFormHeader
          title="Reset Password"
          subtitle="Enter your email to receive a reset link"
        />

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4 animate-card-entrance" style={{ animationDelay: '100ms' }} noValidate>
          <div className="space-y-1.5">
            <Label htmlFor="email">Email</Label>
            <Input
              id="email"
              type="email"
              autoComplete="email"
              aria-invalid={!!errors.email}
              placeholder="you@example.com"
              className={cn(
                'transition-all duration-200',
                errors.email && 'border-danger/50 focus:border-danger'
              )}
              {...register('email')}
            />
            {errors.email && (
              <p className="text-xs text-danger animate-feed-event">{errors.email.message}</p>
            )}
          </div>

          <Button type="submit" className="w-full" disabled={isSubmitting}>
            {isSubmitting ? 'Sending…' : 'Send reset link'}
          </Button>
        </form>

        <p className="text-center text-sm text-text-secondary animate-card-entrance" style={{ animationDelay: '150ms' }}>
          Remember your password?{' '}
          <Link
            to="/login"
            className="text-accent-primary hover:text-accent-primary-hover font-medium transition-colors"
          >
            Sign in
          </Link>
        </p>
      </AuthCard>
    </AuthLayout>
  )
}
