import { useState, type FormEvent } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { adminPredictionsApi } from '@/lib/api/admin-predictions'
import { toast } from '@/stores/toast-store'

const EMPTY = { market_key: '', entity_type: '', entity_id: '', subject_ref: '' }

export function RegeneratePredictionForm() {
  const [values, setValues] = useState(EMPTY)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setSubmitting(true)
    try {
      const result = await adminPredictionsApi.regenerate(values)
      toast.success('Prediction regenerated', `${result.status} · probability ${Math.round(result.probability * 100)}%`)
    } catch (error) {
      toast.danger('Regeneration failed', error instanceof Error ? error.message : undefined)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Regenerate a prediction</CardTitle>
      </CardHeader>
      <CardContent>
        <form className="flex flex-col gap-3" noValidate onSubmit={handleSubmit}>
          <Field label="Market key" value={values.market_key} onChange={(v) => setValues({ ...values, market_key: v })} />
          <Field label="Entity type" value={values.entity_type} onChange={(v) => setValues({ ...values, entity_type: v })} />
          <Field label="Entity id" value={values.entity_id} onChange={(v) => setValues({ ...values, entity_id: v })} />
          <Field label="Subject ref" value={values.subject_ref} onChange={(v) => setValues({ ...values, subject_ref: v })} />
          <Button type="submit" size="sm" loading={submitting}>
            Regenerate
          </Button>
        </form>
      </CardContent>
    </Card>
  )
}

function Field({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  const id = `regen-${label.toLowerCase().replace(/\s+/g, '-')}`
  return (
    <div className="flex flex-col gap-1">
      <Label htmlFor={id}>{label}</Label>
      <Input id={id} required value={value} onChange={(e) => onChange(e.target.value)} />
    </div>
  )
}
