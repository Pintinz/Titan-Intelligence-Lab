import { useState, type FormEvent } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { KeyValueGrid } from '@/components/domain/key-value-grid'
import { mlPlatformApi } from '@/lib/api/ml-platform'
import { toast } from '@/stores/toast-store'
import type { MlFramework } from '@/lib/api/types'

const FRAMEWORKS: MlFramework[] = ['lightgbm', 'xgboost', 'catboost', 'sklearn']

export function BenchmarkForm({ marketKey }: { marketKey: string }) {
  const [algorithm, setAlgorithm] = useState('gbdt')
  const [framework, setFramework] = useState<MlFramework>('lightgbm')
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState<Record<string, unknown> | null>(null)

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setRunning(true)
    try {
      const outcome = await mlPlatformApi.benchmark({ market_key: marketKey, algorithm, framework })
      setResult(outcome)
      toast.success('Benchmark complete', `${outcome.ranking_metric} = ${outcome.ranking_value.toFixed(4)}`)
    } catch (error) {
      toast.danger('Benchmark failed', error instanceof Error ? error.message : undefined)
    } finally {
      setRunning(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Benchmark an algorithm/framework combination</CardTitle>
      </CardHeader>
      <CardContent>
        <form className="flex flex-col gap-3" noValidate onSubmit={handleSubmit}>
          <div className="flex flex-col gap-1">
            <Label htmlFor="benchmark-algorithm">Algorithm</Label>
            <Input id="benchmark-algorithm" value={algorithm} onChange={(e) => setAlgorithm(e.target.value)} required />
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="benchmark-framework">Framework</Label>
            <Select value={framework} onValueChange={(v) => setFramework(v as MlFramework)}>
              <SelectTrigger id="benchmark-framework">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {FRAMEWORKS.map((fw) => (
                  <SelectItem key={fw} value={fw}>
                    {fw}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <Button type="submit" size="sm" loading={running}>
            Run benchmark
          </Button>
          {result && <KeyValueGrid data={result} />}
        </form>
      </CardContent>
    </Card>
  )
}
