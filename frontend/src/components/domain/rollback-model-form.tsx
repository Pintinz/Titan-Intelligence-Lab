import { useState, type FormEvent } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { adminPredictionsApi } from '@/lib/api/admin-predictions'
import { toast } from '@/stores/toast-store'

export function RollbackModelForm() {
  const [marketId, setMarketId] = useState('')
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setSubmitting(true)
    try {
      const result = await adminPredictionsApi.rollbackModel(marketId)
      toast.success('Model rolled back', `${result.model_key} · ${result.status}`)
    } catch (error) {
      toast.danger('Rollback failed', error instanceof Error ? error.message : undefined)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Roll back a model</CardTitle>
      </CardHeader>
      <CardContent>
        <form className="flex flex-col gap-3" noValidate onSubmit={handleSubmit}>
          <div className="flex flex-col gap-1">
            <Label htmlFor="rollback-market-id">Market id</Label>
            <Input id="rollback-market-id" required value={marketId} onChange={(e) => setMarketId(e.target.value)} />
          </div>
          <Button type="submit" variant="danger" size="sm" loading={submitting}>
            Roll back to previous champion
          </Button>
        </form>
      </CardContent>
    </Card>
  )
}
