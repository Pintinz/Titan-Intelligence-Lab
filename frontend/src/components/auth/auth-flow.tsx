import { useState } from 'react'
import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { useNavigate } from 'react-router-dom'
import { supabase, setRememberMe } from '@/lib/supabase'
import { loginSchema, signupSchema, type LoginValues, type SignupValues } from '@/lib/validation/auth-schemas'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { toast } from '@/stores/toast-store'
import { AuthCard } from './auth-card'
import { AuthFormHeader } from './auth-form-header'
import { GoogleSignInButton } from './google-signin-button'
import { cn } from '@/lib/cn'

type AuthMode = 'login' | 'signup'

interface AuthFlowProps {
  initialMode?: AuthMode
}

export function AuthFlow({ initialMode = 'login' }: AuthFlowProps) {
  const navigate = useNavigate()
  const [mode, setMode] = useState<AuthMode>(initialMode)
  const [prevMode, setPrevMode] = useState<AuthMode>(initialMode)
  const [agree, setAgree] = useState(false)

  const loginForm = useForm<LoginValues>({ resolver: zodResolver(loginSchema) })
  const signupForm = useForm<SignupValues>({ resolver: zodResolver(signupSchema) })

  const remember = mode === 'login' ? loginForm.getValues('email') : undefined
  const [rememberMe, setRememberMeState] = useState(true)

  const isLoginMode = mode === 'login'

  async function handleLogin(values: LoginValues) {
    setRememberMe(rememberMe)
    const { error } = await supabase.auth.signInWithPassword(values)
    if (error) {
      toast.danger('Could not sign in', error.message)
      return
    }
    navigate('/app')
  }

  async function handleSignup(values: SignupValues) {
    if (!agree) {
      toast.danger('Please agree to the terms')
      return
    }

    setRememberMe(true)
    const { error } = await supabase.auth.signUp({
      email: values.email,
      password: values.password,
    })

    if (error) {
      toast.danger('Could not create account', error.message)
      return
    }

    toast.success('Account created successfully')
    navigate('/app')
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

            <GoogleSignInButton disabled={loginForm.formState.isSubmitting} />
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
                <a href="/docs" target="_blank" rel="noopener noreferrer" className="text-accent-primary hover:text-accent-primary-hover font-medium">
                  terms of service
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

            <GoogleSignInButton disabled={signupForm.formState.isSubmitting} />
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
