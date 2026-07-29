import { useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

export default function SignupPage() {
  const navigate = useNavigate()

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    // Placeholder: real signup would call Supabase auth
    navigate('/app')
  }

  return (
    <div className="flex min-h-svh items-center justify-center px-4">
      <div className="w-full max-w-sm space-y-6">
        <div className="text-center">
          <span className="inline-flex size-2 rounded-full bg-accent-primary" aria-hidden="true" />
          <h1 className="mt-3 font-display text-2xl font-semibold text-text-primary">TitanIQ</h1>
          <p className="mt-1 text-sm text-text-secondary">Sports Intelligence Platform</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <Label htmlFor="email">Email</Label>
            <Input id="email" type="email" placeholder="you@example.com" required className="mt-1" />
          </div>
          <div>
            <Label htmlFor="password">Password</Label>
            <Input id="password" type="password" placeholder="••••••••" required className="mt-1" />
          </div>
          <div>
            <Label htmlFor="confirm">Confirm password</Label>
            <Input id="confirm" type="password" placeholder="••••••••" required className="mt-1" />
          </div>

          <Button type="submit" className="w-full">
            Create account
          </Button>
        </form>

        <p className="text-center text-sm text-text-secondary">
          Already have an account?{' '}
          <Button variant="ghost" onClick={() => navigate('/login')} className="p-0 text-accent-primary">
            Sign in
          </Button>
        </p>
      </div>
    </div>
  )
}
