import { useState } from 'react'
import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { useLocation, useNavigate, type Location } from 'react-router-dom'
import { supabase, setRememberMe } from '@/lib/supabase'
import { isNativePlatform } from '@/lib/capacitor'
import { signInWithGoogleNative } from '@/lib/native-oauth'
import { loginSchema, signupSchema, type LoginValues, type SignupValues } from '@/lib/validation/auth-schemas'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { toast } from '@/stores/toast-store'
import { AuthCard } from './auth-card'
import { AuthFormHeader } from './auth-form-header'
import { GoogleSignInButton } from './google-signin-button'
import { cn } from '@/lib/cn'

// Most Supabase auth errors carry a real, readable `.message` ("Invalid login credentials",
// etc.), but a handful of server-side failure shapes (seen live: a 500 from a misconfigured SMTP
// provider) leave the client SDK unable to extract one, and `.message` ends up as the literal
// string "{}" — worse than no message at all, since it reads as a broken app rather than a real
// error. Never show that (or an empty string) verbatim; fall back to something a visitor can act on.
function readableAuthErrorMessage(error: { message?: string } | null | undefined, fallback: string): string {
  const message = error?.message?.trim()
  if (!message || message.startsWith('{') || message.startsWith('[')) return fallback
  return message
}

type AuthMode = 'login' | 'signup'

interface AuthFlowProps {
  initialMode?: AuthMode
}

export function AuthFlow({ initialMode = 'login' }: AuthFlowProps) {
  const navigate = useNavigate()
  const location = useLocation()
  // Set by ProtectedRoute when it redirects an unauthenticated visit here (e.g. clicking "Get
  // Pro" while logged out) — send them back to exactly where they were headed, query string and
  // all. A plain, direct login/signup (no `from` — arrived at /login on its own, not redirected
  // by a protected route) has nothing to return to, so it goes to the landing page, not checkout
  // or the dashboard.
  const from = (location.state as { from?: Location } | null)?.from
  const returnTo = from ? `${from.pathname}${from.search}` : '/'
  const [mode, setMode] = useState<AuthMode>(initialMode)
  const [prevMode, setPrevMode] = useState<AuthMode>(initialMode)
  const [agree, setAgree] = useState(false)

  const loginForm = useForm<LoginValues>({ resolver: zodResolver(loginSchema) })
  const signupForm = useForm<SignupValues>({ resolver: zodResolver(signupSchema) })

  const [rememberMe, setRememberMeState] = useState(true)
  const [googleLoading, setGoogleLoading] = useState(false)

  async function handleGoogleSignIn() {
    // OAuth is a real cross-origin redirect to Google and back, not client-side routing — the
    // in-memory `returnTo` above would be lost, so it travels via the callback URL's query string
    // instead (read back by AuthCallbackPage). Session persistence for an OAuth sign-in always
    // behaves like "remember me" checked — there's no equivalent checkbox in Google's own consent
    // flow to honor a "this device only" choice for.
    setRememberMe(true)
    setGoogleLoading(true)

    // Native: Google blocks OAuth inside an embedded WebView, so this opens the system browser
    // and returns via a titaniq:// deep link instead of a same-origin redirect (see
    // lib/native-oauth.ts — the deep-link handler routes back into this exact same
    // AuthCallbackPage, no separate native session-exchange logic).
    if (isNativePlatform()) {
      const { error } = await signInWithGoogleNative(returnTo)
      if (error) {
        setGoogleLoading(false)
        toast.danger('Could not sign in with Google', readableAuthErrorMessage({ message: error }, 'Something went wrong starting Google sign-in. Try again.'))
      }
      // On success the system browser is now in front — nothing else to do here until the
      // titaniq:// deep link returns control to the app.
      return
    }

    const { error } = await supabase.auth.signInWithOAuth({
      provider: 'google',
      options: { redirectTo: `${window.location.origin}/auth/callback?returnTo=${encodeURIComponent(returnTo)}` },
    })
    if (error) {
      setGoogleLoading(false)
      toast.danger('Could not sign in with Google', readableAuthErrorMessage(error, 'Something went wrong starting Google sign-in. Try again.'))
      return
    }
    // On success the browser navigates away to Google's consent screen immediately — nothing
    // else to do here, and googleLoading intentionally never resets on this path (the page is
    // about to unload).
  }

  const isLoginMode = mode === 'login'

  async function handleLogin(values: LoginValues) {
    setRememberMe(rememberMe)
    try {
      const { error } = await supabase.auth.signInWithPassword(values)
      if (error) {
        toast.danger('Could not sign in', readableAuthErrorMessage(error, 'Something went wrong signing you in. Try again.'))
        return
      }
      navigate(returnTo)
    } catch {
      // supabase.auth.* rejects (rather than returning {error}) on a genuine network failure —
      // offline, DNS, the Supabase project unreachable. Without this, that case silently
      // re-enables the button with zero feedback, the least helpful possible failure mode for
      // exactly the "issues with login" this is meant to prevent.
      toast.danger('Could not sign in', 'Check your connection and try again.')
    }
  }

  async function handleSignup(values: SignupValues) {
    if (!agree) {
      toast.danger('Please agree to the terms')
      return
    }

    setRememberMe(true)
    try {
      const { data, error } = await supabase.auth.signUp({
        email: values.email,
        password: values.password,
      })

      if (error) {
        toast.danger('Could not create account', readableAuthErrorMessage(error, 'Something went wrong creating your account. Try again in a moment.'))
        return
      }

      if (data.session) {
        // Email confirmation is off for this project — signUp already returns an active session.
        toast.success('Account created successfully')
        navigate(returnTo)
        return
      }

      // Email confirmation is required — there's no session yet, so navigating into a protected
      // route would just bounce straight back to /login with no explanation. Tell the visitor
      // what to do instead, and drop them at login (which will carry the same `returnTo` forward
      // once they actually have a session).
      toast.success('Check your email to confirm your account', `We sent a confirmation link to ${values.email}.`)
      toggleMode('login')
    } catch {
      toast.danger('Could not create account', 'Check your connection and try again.')
    }
  }

  const toggleMode = (newMode: AuthMode) => {
    setPrevMode(mode)
    setMode(newMode)
    setAgree(false)
    if (newMode === 'login') {
      signupForm.reset()
    } else {
      loginForm.reset()
    }
  }

  const isTransitioningToSignup = prevMode === 'login' && mode === 'signup'
  const isTransitioningToLogin = prevMode === 'signup' && mode === 'login'

  return (
    <AuthCard>
      <div className="relative">
        {/* Login Form */}
        <div
          className={cn(
            'transition-all duration-300 ease-in-out',
            isLoginMode
              ? cn(
                  'opacity-100 visible',
                  isTransitioningToLogin && 'animate-form-morph-in-left'
                )
              : 'opacity-0 invisible absolute inset-0'
          )}
        >
          <AuthFormHeader
            title="Welcome Back"
            subtitle="See every match through intelligence."
          />

          <form onSubmit={loginForm.handleSubmit(handleLogin)} className="space-y-4" noValidate>
            <div className="space-y-1.5 animate-field-stagger" style={{ animationDelay: '50ms' }}>
              <Label htmlFor="login-email">Email</Label>
              <Input
                id="login-email"
                type="email"
                autoComplete="email"
                aria-invalid={!!loginForm.formState.errors.email}
                placeholder="you@example.com"
                className={cn(
                  'transition-all duration-200',
                  loginForm.formState.errors.email && 'border-danger/50 focus:border-danger'
                )}
                {...loginForm.register('email')}
              />
              {loginForm.formState.errors.email && (
                <p className="text-xs text-danger animate-feed-event">{loginForm.formState.errors.email.message}</p>
              )}
            </div>

            <div className="space-y-1.5 animate-field-stagger" style={{ animationDelay: '100ms' }}>
              <div className="flex items-center justify-between">
                <Label htmlFor="login-password">Password</Label>
                <a href="/forgot-password" className="text-xs text-accent-primary hover:text-accent-primary-hover transition-colors">
                  Forgot?
                </a>
              </div>
              <Input
                id="login-password"
                type="password"
                autoComplete="current-password"
                aria-invalid={!!loginForm.formState.errors.password}
                placeholder="••••••••"
                className={cn(
                  'transition-all duration-200',
                  loginForm.formState.errors.password && 'border-danger/50 focus:border-danger'
                )}
                {...loginForm.register('password')}
              />
              {loginForm.formState.errors.password && (
                <p className="text-xs text-danger animate-feed-event">{loginForm.formState.errors.password.message}</p>
              )}
            </div>

            <div className="flex items-center gap-2 text-sm animate-field-stagger" style={{ animationDelay: '150ms' }}>
              <input
                type="checkbox"
                id="login-remember"
                checked={rememberMe}
                onChange={(e) => setRememberMeState(e.target.checked)}
                className="size-3.5 rounded border-border-default accent-[var(--color-accent-primary)] transition-all"
              />
              <label htmlFor="login-remember" className="text-text-secondary cursor-pointer">
                Remember me
              </label>
            </div>

            <Button
              type="submit"
              className="w-full animate-field-stagger"
              style={{ animationDelay: '200ms' }}
              disabled={loginForm.formState.isSubmitting}
            >
              {loginForm.formState.isSubmitting ? 'Signing in…' : 'Sign in'}
            </Button>
          </form>

          <div className="space-y-3 animate-field-stagger" style={{ animationDelay: '250ms' }}>
            <div className="relative">
              <div className="absolute inset-0 flex items-center">
                <div className="w-full border-t border-border-default/20" />
              </div>
              <div className="relative flex justify-center text-xs">
                <span className="bg-bg-secondary/40 px-2 text-text-muted">or</span>
              </div>
            </div>

            <GoogleSignInButton
              disabled={loginForm.formState.isSubmitting}
              isLoading={googleLoading}
              onClick={handleGoogleSignIn}
            />
          </div>

          <p className="text-center text-sm text-text-secondary animate-field-stagger" style={{ animationDelay: '350ms' }}>
            Don't have an account?{' '}
            <button
              type="button"
              onClick={() => toggleMode('signup')}
              className="text-accent-primary hover:text-accent-primary-hover font-medium transition-colors"
            >
              Sign up
            </button>
          </p>
        </div>

        {/* Signup Form */}
        <div
          className={cn(
            'transition-all duration-300 ease-in-out',
            !isLoginMode
              ? cn(
                  'opacity-100 visible',
                  isTransitioningToSignup && 'animate-form-morph-in-right'
                )
              : 'opacity-0 invisible absolute inset-0'
          )}
        >
          <AuthFormHeader
            title="Create Account"
            subtitle="See every match through intelligence."
          />

          <form onSubmit={signupForm.handleSubmit(handleSignup)} className="space-y-4" noValidate>
            <div className="space-y-1.5 animate-field-stagger" style={{ animationDelay: '50ms' }}>
              <Label htmlFor="signup-email">Email</Label>
              <Input
                id="signup-email"
                type="email"
                autoComplete="email"
                aria-invalid={!!signupForm.formState.errors.email}
                placeholder="you@example.com"
                className={cn(
                  'transition-all duration-200',
                  signupForm.formState.errors.email && 'border-danger/50 focus:border-danger'
                )}
                {...signupForm.register('email')}
              />
              {signupForm.formState.errors.email && (
                <p className="text-xs text-danger animate-feed-event">{signupForm.formState.errors.email.message}</p>
              )}
            </div>

            <div className="space-y-1.5 animate-field-stagger" style={{ animationDelay: '100ms' }}>
              <Label htmlFor="signup-password">Password</Label>
              <Input
                id="signup-password"
                type="password"
                autoComplete="new-password"
                aria-invalid={!!signupForm.formState.errors.password}
                placeholder="At least 8 characters"
                className={cn(
                  'transition-all duration-200',
                  signupForm.formState.errors.password && 'border-danger/50 focus:border-danger'
                )}
                {...signupForm.register('password')}
              />
              {signupForm.formState.errors.password && (
                <p className="text-xs text-danger animate-feed-event">{signupForm.formState.errors.password.message}</p>
              )}
            </div>

            <div className="space-y-1.5 animate-field-stagger" style={{ animationDelay: '150ms' }}>
              <Label htmlFor="signup-confirm">Confirm Password</Label>
              <Input
                id="signup-confirm"
                type="password"
                autoComplete="new-password"
                aria-invalid={!!signupForm.formState.errors.confirmPassword}
                placeholder="••••••••"
                className={cn(
                  'transition-all duration-200',
                  signupForm.formState.errors.confirmPassword && 'border-danger/50 focus:border-danger'
                )}
                {...signupForm.register('confirmPassword')}
              />
              {signupForm.formState.errors.confirmPassword && (
                <p className="text-xs text-danger animate-feed-event">{signupForm.formState.errors.confirmPassword.message}</p>
              )}
            </div>

            <div className="flex items-start gap-2 text-sm animate-field-stagger" style={{ animationDelay: '200ms' }}>
              <input
                type="checkbox"
                id="signup-agree"
                checked={agree}
                onChange={(e) => setAgree(e.target.checked)}
                className="mt-0.5 size-3.5 rounded border-border-default accent-[var(--color-accent-primary)] transition-all cursor-pointer"
              />
              <label htmlFor="signup-agree" className="text-text-secondary cursor-pointer">
                I agree to the{' '}
                <a href="/terms" target="_blank" rel="noopener noreferrer" className="text-accent-primary hover:text-accent-primary-hover font-medium">
                  terms of service
                </a>{' '}
                and{' '}
                <a href="/privacy" target="_blank" rel="noopener noreferrer" className="text-accent-primary hover:text-accent-primary-hover font-medium">
                  privacy policy
                </a>
              </label>
            </div>

            <Button
              type="submit"
              className="w-full animate-field-stagger"
              style={{ animationDelay: '250ms' }}
              disabled={signupForm.formState.isSubmitting || !agree}
            >
              {signupForm.formState.isSubmitting ? 'Creating account…' : 'Create account'}
            </Button>
          </form>

          <div className="space-y-3 animate-field-stagger" style={{ animationDelay: '300ms' }}>
            <div className="relative">
              <div className="absolute inset-0 flex items-center">
                <div className="w-full border-t border-border-default/20" />
              </div>
              <div className="relative flex justify-center text-xs">
                <span className="bg-bg-secondary/40 px-2 text-text-muted">or</span>
              </div>
            </div>

            <GoogleSignInButton
              disabled={signupForm.formState.isSubmitting}
              isLoading={googleLoading}
              onClick={handleGoogleSignIn}
            />
          </div>

          <p className="text-center text-sm text-text-secondary animate-field-stagger" style={{ animationDelay: '350ms' }}>
            Already have an account?{' '}
            <button
              type="button"
              onClick={() => toggleMode('login')}
              className="text-accent-primary hover:text-accent-primary-hover font-medium transition-colors"
            >
              Sign in
            </button>
          </p>
        </div>
      </div>
    </AuthCard>
  )
}
