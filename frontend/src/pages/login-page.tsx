import { useState } from 'react'
import { Link, type Location, useLocation, useNavigate } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Checkbox } from '@/components/ui/checkbox'
import { Separator } from '@/components/ui/separator'
import { OAuthButtons } from '@/components/auth/oauth-buttons'
import { AuthSplitLayout } from '@/components/layout/auth-split-layout'
import { loginSchema, magicLinkSchema, type LoginValues, type MagicLinkValues } from '@/lib/validation/auth-schemas'
import { supabase, setRememberMe } from '@/lib/supabase'
import { toast } from '@/stores/toast-store'

export function LoginPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const [mode, setMode] = useState<'password' | 'magic-link'>('password')
  const [remember, setRemember] = useState(true)
  const from = (location.state as { from?: Location } | null)?.from?.pathname ?? '/app'

  const passwordForm = useForm<LoginValues>({ resolver: zodResolver(loginSchema) })
  const magicLinkForm = useForm<MagicLinkValues>({ resolver: zodResolver(magicLinkSchema) })

  async function onPasswordSubmit(values: LoginValues) {
    setRememberMe(remember)
    const { error } = await supabase.auth.signInWithPassword(values)
    if (error) {
      toast.danger('Sign-in failed', error.message)
      return
    }
    navigate(from, { replace: true })
  }

  async function onMagicLinkSubmit(values: MagicLinkValues) {
    setRememberMe(remember)
    const { error } = await supabase.auth.signInWithOtp({
      email: values.email,
      options: { emailRedirectTo: `${window.location.origin}/auth/callback` },
    })
    if (error) {
      toast.danger('Could not send magic link', error.message)
      return
    }
    toast.success('Check your email', `We sent a sign-in link to ${values.email}`)
  }

  return (
    <AuthSplitLayout
      eyebrow="Welcome back"
      title="Sign in to keep building on calibrated predictions."
      tagline="Your saved markets, prediction history, and knowledge graph context pick up right where you left off."
    >
      <h1 className="font-display text-xl font-semibold text-text-primary">Sign in to TitanIQ</h1>
      <p className="mt-1 text-sm text-text-secondary">Sports Intelligence Beyond Prediction</p>

      <div className="mt-6">
        <OAuthButtons />
      </div>

      <div className="my-6 flex items-center gap-3">
        <Separator className="flex-1" />
        <span className="text-xs text-text-muted">or</span>
        <Separator className="flex-1" />
      </div>

      {mode === 'password' ? (
        <form className="flex flex-col gap-4" noValidate onSubmit={passwordForm.handleSubmit(onPasswordSubmit)}>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="email">Email</Label>
            <Input id="email" type="email" autoComplete="email" {...passwordForm.register('email')} />
            {passwordForm.formState.errors.email && (
              <p className="text-xs text-danger">{passwordForm.formState.errors.email.message}</p>
            )}
          </div>
          <div className="flex flex-col gap-1.5">
            <div className="flex items-center justify-between">
              <Label htmlFor="password">Password</Label>
              <Link to="/forgot-password" className="text-xs text-accent-primary hover:underline">
                Forgot password?
              </Link>
            </div>
            <Input id="password" type="password" autoComplete="current-password" {...passwordForm.register('password')} />
            {passwordForm.formState.errors.password && (
              <p className="text-xs text-danger">{passwordForm.formState.errors.password.message}</p>
            )}
          </div>
          <div className="flex items-center gap-2">
            <Checkbox id="remember-me" checked={remember} onCheckedChange={(v) => setRemember(v === true)} />
            <Label htmlFor="remember-me" className="text-xs font-normal text-text-secondary">
              Remember me on this device
            </Label>
          </div>
          <Button type="submit" loading={passwordForm.formState.isSubmitting} className="mt-1">
            Sign in
          </Button>
          <button
            type="button"
            className="text-xs text-text-secondary hover:text-text-primary"
            onClick={() => setMode('magic-link')}
          >
            Use a magic link instead
          </button>
        </form>
      ) : (
        <form className="flex flex-col gap-4" noValidate onSubmit={magicLinkForm.handleSubmit(onMagicLinkSubmit)}>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="magic-email">Email</Label>
            <Input id="magic-email" type="email" autoComplete="email" {...magicLinkForm.register('email')} />
            {magicLinkForm.formState.errors.email && (
              <p className="text-xs text-danger">{magicLinkForm.formState.errors.email.message}</p>
            )}
          </div>
          <Button type="submit" loading={magicLinkForm.formState.isSubmitting} className="mt-1">
            Send magic link
          </Button>
          <button
            type="button"
            className="text-xs text-text-secondary hover:text-text-primary"
            onClick={() => setMode('password')}
          >
            Use a password instead
          </button>
        </form>
      )}

      <p className="mt-6 text-center text-sm text-text-secondary">
        No account?{' '}
        <Link to="/signup" className="text-accent-primary hover:underline">
          Sign up
        </Link>
      </p>
    </AuthSplitLayout>
  )
}
