import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Separator } from '@/components/ui/separator'
import { OAuthButtons } from '@/components/auth/oauth-buttons'
import { AuthSplitLayout } from '@/components/layout/auth-split-layout'
import { signupSchema, type SignupValues } from '@/lib/validation/auth-schemas'
import { supabase } from '@/lib/supabase'
import { toast } from '@/stores/toast-store'

export function SignupPage() {
  const [submitted, setSubmitted] = useState<string | null>(null)
  const form = useForm<SignupValues>({ resolver: zodResolver(signupSchema) })

  async function onSubmit(values: SignupValues) {
    const { error } = await supabase.auth.signUp({
      email: values.email,
      password: values.password,
      options: { emailRedirectTo: `${window.location.origin}/auth/callback` },
    })
    if (error) {
      toast.danger('Sign-up failed', error.message)
      return
    }
    setSubmitted(values.email)
  }

  if (submitted) {
    return (
      <AuthSplitLayout
        eyebrow="Almost there"
        title="One more step."
        tagline="Confirm your email and your first prediction market is a click away."
      >
        <div className="text-center">
          <h1 className="font-display text-xl font-semibold text-text-primary">Check your email</h1>
          <p className="mt-2 text-sm text-text-secondary">
            We sent a confirmation link to <span className="text-text-primary">{submitted}</span>. Verify it to
            activate your account.
          </p>
          <Link to="/login" className="mt-6 inline-block text-sm text-accent-primary hover:underline">
            Back to sign in
          </Link>
        </div>
      </AuthSplitLayout>
    )
  }

  return (
    <AuthSplitLayout
      eyebrow="Get started"
      title="Sports intelligence, calibrated and explained."
      tagline="Free to start — every prediction ships with a confidence breakdown and feature-level explanation."
    >
      <h1 className="font-display text-xl font-semibold text-text-primary">Create your account</h1>
      <p className="mt-1 text-sm text-text-secondary">Start with a free TitanIQ account</p>

      <div className="mt-6">
        <OAuthButtons />
      </div>

      <div className="my-6 flex items-center gap-3">
        <Separator className="flex-1" />
        <span className="text-xs text-text-muted">or</span>
        <Separator className="flex-1" />
      </div>

      <form className="flex flex-col gap-4" noValidate onSubmit={form.handleSubmit(onSubmit)}>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="email">Email</Label>
          <Input id="email" type="email" autoComplete="email" {...form.register('email')} />
          {form.formState.errors.email && <p className="text-xs text-danger">{form.formState.errors.email.message}</p>}
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="password">Password</Label>
          <Input id="password" type="password" autoComplete="new-password" {...form.register('password')} />
          {form.formState.errors.password && (
            <p className="text-xs text-danger">{form.formState.errors.password.message}</p>
          )}
        </div>
        <Button type="submit" loading={form.formState.isSubmitting} className="mt-1">
          Create account
        </Button>
      </form>

      <p className="mt-6 text-center text-sm text-text-secondary">
        Already have an account?{' '}
        <Link to="/login" className="text-accent-primary hover:underline">
          Sign in
        </Link>
      </p>
    </AuthSplitLayout>
  )
}
