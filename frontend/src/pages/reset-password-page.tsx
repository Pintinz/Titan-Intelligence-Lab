import { useNavigate } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { AuthSplitLayout } from '@/components/layout/auth-split-layout'
import { resetPasswordSchema, type ResetPasswordValues } from '@/lib/validation/auth-schemas'
import { supabase } from '@/lib/supabase'
import { toast } from '@/stores/toast-store'

/**
 * Landed on via the emailed reset link — Supabase's `detectSessionInUrl` (src/lib/supabase.ts)
 * already exchanged the recovery token for a session before this component mounts, so this page
 * only needs to call `updateUser`, not handle the token itself.
 */
export function ResetPasswordPage() {
  const navigate = useNavigate()
  const form = useForm<ResetPasswordValues>({ resolver: zodResolver(resetPasswordSchema) })

  async function onSubmit(values: ResetPasswordValues) {
    const { error } = await supabase.auth.updateUser({ password: values.password })
    if (error) {
      toast.danger('Could not update password', error.message)
      return
    }
    toast.success('Password updated')
    navigate('/app', { replace: true })
  }

  return (
    <AuthSplitLayout
      eyebrow="Account security"
      title="Choose a strong new password."
      tagline="You'll be signed in with your new password right away."
    >
      <h1 className="font-display text-xl font-semibold text-text-primary">Choose a new password</h1>
      <form className="mt-6 flex flex-col gap-4" noValidate onSubmit={form.handleSubmit(onSubmit)}>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="password">New password</Label>
          <Input id="password" type="password" autoComplete="new-password" {...form.register('password')} />
          {form.formState.errors.password && (
            <p className="text-xs text-danger">{form.formState.errors.password.message}</p>
          )}
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="confirmPassword">Confirm password</Label>
          <Input id="confirmPassword" type="password" autoComplete="new-password" {...form.register('confirmPassword')} />
          {form.formState.errors.confirmPassword && (
            <p className="text-xs text-danger">{form.formState.errors.confirmPassword.message}</p>
          )}
        </div>
        <Button type="submit" loading={form.formState.isSubmitting}>
          Update password
        </Button>
      </form>
    </AuthSplitLayout>
  )
}
