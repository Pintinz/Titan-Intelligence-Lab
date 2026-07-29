import { useState } from 'react'
import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { Link, useNavigate } from 'react-router-dom'
import { supabase, setRememberMe } from '@/lib/supabase'
import { loginSchema, type LoginValues } from '@/lib/validation/auth-schemas'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { toast } from '@/stores/toast-store'

export default function LoginPage() {
  const navigate = useNavigate()
  const [remember, setRemember] = useState(true)
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginValues>({ resolver: zodResolver(loginSchema) })

  async function onSubmit(values: LoginValues) {
    setRememberMe(remember)
    const { error } = await supabase.auth.signInWithPassword(values)
    if (error) {
      toast.danger('Could not sign in', error.message)
      return
    }
    navigate('/app')
  }

  return (
    <div className="flex min-h-svh items-center justify-center bg-bg-primary px-6">
      <div className="w-full max-w-sm space-y-6">
        <div className="space-y-1 text-center">
          <span className="mx-auto block size-2 rounded-full bg-accent-primary" aria-hidden="true" />
          <h1 className="font-display text-xl font-semibold text-text-primary">Sign in to TitanIQ</h1>
          <p className="text-sm text-text-secondary">See every match through intelligence.</p>
        </div>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
          <div className="space-y-1.5">
            <Label htmlFor="email">Email</Label>
            <Input
              id="email"
              type="email"
              autoComplete="email"
              aria-invalid={!!errors.email}
              {...register('email')}
            />
            {errors.email && <p className="text-xs text-danger">{errors.email.message}</p>}
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="password">Password</Label>
            <Input
              id="password"
              type="password"
              autoComplete="current-password"
              aria-invalid={!!errors.password}
              {...register('password')}
            />
            {errors.password && <p className="text-xs text-danger">{errors.password.message}</p>}
          </div>

          <div className="flex items-center justify-between text-sm">
            <label className="flex items-center gap-2 text-text-secondary">
              <input
                type="checkbox"
                checked={remember}
                onChange={(e) => setRemember(e.target.checked)}
                className="size-3.5 rounded border-border-default accent-[var(--color-accent-primary)]"
              />
              Remember me
            </label>
            <Link to="/forgot-password" className="text-accent-primary hover:text-accent-primary-hover">
              Forgot password?
            </Link>
          </div>

          <Button type="submit" className="w-full" disabled={isSubmitting}>
            {isSubmitting ? 'Signing in…' : 'Sign in'}
          </Button>
        </form>

        <p className="text-center text-sm text-text-secondary">
          Don't have an account?{' '}
          <Link to="/signup" className="text-accent-primary hover:text-accent-primary-hover">
            Sign up
          </Link>
        </p>
      </div>
    </div>
  )
}
