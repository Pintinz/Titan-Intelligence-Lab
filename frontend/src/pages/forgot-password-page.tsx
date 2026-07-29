import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { AuthSplitLayout } from '@/components/layout/auth-split-layout'
import { forgotPasswordSchema, type ForgotPasswordValues } from '@/lib/validation/auth-schemas'
import { supabase } from '@/lib/supabase'
import { toast } from '@/stores/toast-store'

export function ForgotPasswordPage() {
  const [sent, setSent] = useState(false)
  const form = useForm<ForgotPasswordValues>({ resolver: zodResolver(forgotPasswordSchema) })

  async function onSubmit(values: ForgotPasswordValues) {
    const { error } = await supabase.auth.resetPasswordForEmail(values.email, {
      redirectTo: `${window.location.origin}/reset-password`,
    })
    if (error) {
      toast.danger('Could not send reset link', error.message)
      return
    }
    setSent(true)
  }

  return (
    <AuthSplitLayout
      eyebrow="Account recovery"
      title="Get back to your predictions."
      tagline="We'll email you a secure link to set a new password."
    >
      <h1 className="font-display text-xl font-semibold text-text-primary">Reset your password</h1>
      {sent ? (
        <p className="mt-3 text-sm text-text-secondary">
          If an account exists for that email, a reset link is on its way.
        </p>
      ) : (
        <form className="mt-6 flex flex-col gap-4" noValidate onSubmit={form.handleSubmit(onSubmit)}>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="email">Email</Label>
            <Input id="email" type="email" autoComplete="email" {...form.register('email')} />
            {form.formState.errors.email && (
              <p className="text-xs text-danger">{form.formState.errors.email.message}</p>
            )}
          </div>
          <Button type="submit" loading={form.formState.isSubmitting}>
            Send reset link
          </Button>
        </form>
      )}
      <Link to="/login" className="mt-6 inline-block text-sm text-accent-primary hover:underline">
        Back to sign in
      </Link>
    </AuthSplitLayout>
  )
}
