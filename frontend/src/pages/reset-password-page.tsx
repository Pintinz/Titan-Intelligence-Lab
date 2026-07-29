import { useEffect, useState } from 'react'
import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { useNavigate } from 'react-router-dom'
import { supabase } from '@/lib/supabase'
import { resetPasswordSchema, type ResetPasswordValues } from '@/lib/validation/auth-schemas'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { toast } from '@/stores/toast-store'
import { AuthLayout } from '@/components/auth/auth-layout'
import { AuthCard } from '@/components/auth/auth-card'
import { AuthFormHeader } from '@/components/auth/auth-form-header'
import { cn } from '@/lib/cn'

export default function ResetPasswordPage() {
  const navigate = useNavigate()
  const [isReady, setIsReady] = useState(false)
  const {
    register,
    handleSubmit,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<ResetPasswordValues>({ resolver: zodResolver(resetPasswordSchema) })

  const password = watch('password')

  useEffect(() => {
    const checkSession = async () => {
      const { data } = await supabase.auth.getSession()
      if (!data.session) {
        toast.danger('Invalid or expired reset link')
        navigate('/forgot-password')
        return
      }
      setIsReady(true)
    }

    void checkSession()
  }, [navigate])

  async function onSubmit(values: ResetPasswordValues) {
    const { error } = await supabase.auth.updateUser({
      password: values.password,
    })

    if (error) {
      toast.danger('Could not reset password', error.message)
      return
    }

    toast.success('Password reset successfully')
    navigate('/app')
  }

  if (!isReady) {
    return (
      <AuthLayout>
        <AuthCard>
          <div className="flex flex-col items-center justify-center py-8">
            <div className="animate-spin size-8 border-2 border-accent-primary border-t-transparent rounded-full" />
            <p className="text-sm text-text-muted mt-4">Loading…</p>
          </div>
        </AuthCard>
      </AuthLayout>
    )
  }

  return (
    <AuthLayout>
      <AuthCard>
        <AuthFormHeader
          title="Create New Password"
          subtitle="Enter a new password for your TitanIQ account"
        />

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4 animate-card-entrance" style={{ animationDelay: '100ms' }} noValidate>
          <div className="space-y-1.5">
            <Label htmlFor="password">Password</Label>
            <Input
              id="password"
              type="password"
              autoComplete="new-password"
              aria-invalid={!!errors.password}
              placeholder="At least 8 characters"
              className={cn(
                'transition-all duration-200',
                errors.password && 'border-danger/50 focus:border-danger'
              )}
              {...register('password')}
            />
            {errors.password && (
              <p className="text-xs text-danger animate-feed-event">{errors.password.message}</p>
            )}
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="confirmPassword">Confirm Password</Label>
            <Input
              id="confirmPassword"
              type="password"
              autoComplete="new-password"
              aria-invalid={!!errors.confirmPassword}
              placeholder="••••••••"
              className={cn(
                'transition-all duration-200',
                errors.confirmPassword && 'border-danger/50 focus:border-danger'
              )}
              {...register('confirmPassword')}
            />
            {errors.confirmPassword && (
              <p className="text-xs text-danger animate-feed-event">{errors.confirmPassword.message}</p>
            )}
          </div>

          <Button type="submit" className="w-full" disabled={isSubmitting}>
            {isSubmitting ? 'Resetting password…' : 'Reset password'}
          </Button>
        </form>
      </AuthCard>
    </AuthLayout>
  )
}
