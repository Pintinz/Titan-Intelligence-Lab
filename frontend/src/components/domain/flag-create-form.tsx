import { useState, type FormEvent } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input, Textarea } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { adminPlatformApi } from '@/lib/api/admin-platform'
import { queryClient } from '@/lib/query-client'
import { toast } from '@/stores/toast-store'

const EMPTY = { key: '', name: '', description: '' }

export function FlagCreateForm() {
  const [values, setValues] = useState(EMPTY)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setSubmitting(true)
    try {
      await adminPlatformApi.createFlag(values)
      toast.success('Feature flag created')
      setValues(EMPTY)
      void queryClient.invalidateQueries({ queryKey: ['admin', 'flags'] })
    } catch (error) {
      toast.danger('Could not create flag', error instanceof Error ? error.message : undefined)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Create a feature flag</CardTitle>
      </CardHeader>
      <CardContent>
        <form className="flex flex-col gap-3" noValidate onSubmit={handleSubmit}>
          <div className="flex flex-col gap-1">
            <Label htmlFor="flag-key">Key</Label>
            <Input id="flag-key" required value={values.key} onChange={(e) => setValues({ ...values, key: e.target.value })} />
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="flag-name">Name</Label>
            <Input id="flag-name" required value={values.name} onChange={(e) => setValues({ ...values, name: e.target.value })} />
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="flag-description">Description</Label>
            <Textarea
              id="flag-description"
              value={values.description}
              onChange={(e) => setValues({ ...values, description: e.target.value })}
            />
          </div>
          <Button type="submit" size="sm" loading={submitting}>
            Create flag
          </Button>
        </form>
      </CardContent>
    </Card>
  )
}
