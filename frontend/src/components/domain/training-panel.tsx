import { useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Badge } from '@/components/ui/badge'
import { Stepper } from '@/components/domain/stepper'
import { mlPlatformApi } from '@/lib/api/ml-platform'
import { useAuthStore } from '@/stores/auth-store'
import { toast } from '@/stores/toast-store'
import type { DatasetDto } from '@/lib/api/types'

const STEPS = [
  { id: 'build', label: 'Build dataset' },
  { id: 'validate', label: 'Validate' },
  { id: 'approve', label: 'Approve' },
  { id: 'select-champion', label: 'Select champion' },
]

/**
 * Drives the Dataset Platform + Automatic Model Selection workflow
 * (build -> validate -> approve -> select-champion, docs/training_pipeline.md) for one market.
 * Local wizard state only — the dataset/experiment records themselves are the real persisted
 * state on the backend; this component just walks a session through the sequence of calls.
 */
export function TrainingPanel({ marketKey, onChampionSelected }: { marketKey: string; onChampionSelected: () => void }) {
  const approvedBy = useAuthStore((s) => s.profile?.email) ?? 'unknown-admin'
  const [dataset, setDataset] = useState<DatasetDto | null>(null)
  const [modelKeyPrefix, setModelKeyPrefix] = useState('')
  const [targetType, setTargetType] = useState<'classification' | 'regression'>('classification')
  const [busyStep, setBusyStep] = useState<string | null>(null)
  const [result, setResult] = useState<{ algorithm: string; framework: string; ranking_metric: string; ranking_value: number } | null>(
    null,
  )

  const currentStepId =
    dataset?.status === 'approved'
      ? 'select-champion'
      : dataset?.status === 'validated'
        ? 'approve'
        : dataset
          ? 'validate'
          : 'build'

  async function handleBuild() {
    setBusyStep('build')
    try {
      const built = await mlPlatformApi.buildDataset(marketKey)
      setDataset(built)
      if (built.quality_issues.length > 0) {
        toast.warning('Dataset built with quality issues', built.quality_issues.join('; '))
      } else {
        toast.success('Dataset built', `${built.sample_count} samples, version ${built.version}`)
      }
    } catch (error) {
      toast.danger('Could not build dataset', error instanceof Error ? error.message : undefined)
    } finally {
      setBusyStep(null)
    }
  }

  async function handleValidate() {
    if (!dataset) return
    setBusyStep('validate')
    try {
      const { status } = await mlPlatformApi.validateDataset(dataset.id)
      setDataset({ ...dataset, status })
      toast.success('Dataset validated', `Status: ${status}`)
    } catch (error) {
      toast.danger('Validation failed', error instanceof Error ? error.message : undefined)
    } finally {
      setBusyStep(null)
    }
  }

  async function handleApprove() {
    if (!dataset) return
    setBusyStep('approve')
    try {
      const { status } = await mlPlatformApi.approveDataset(dataset.id, approvedBy)
      setDataset({ ...dataset, status })
      toast.success('Dataset approved')
    } catch (error) {
      toast.danger('Approval failed', error instanceof Error ? error.message : undefined)
    } finally {
      setBusyStep(null)
    }
  }

  async function handleSelectChampion() {
    if (!modelKeyPrefix.trim()) {
      toast.danger('Model key prefix is required')
      return
    }
    setBusyStep('select-champion')
    try {
      const outcome = await mlPlatformApi.selectChampion({
        market_key: marketKey,
        model_key_prefix: modelKeyPrefix.trim(),
        target_type: targetType,
      })
      setResult(outcome)
      toast.success('Champion selected', `${outcome.algorithm} (${outcome.framework}) — ${outcome.ranking_metric} ${outcome.ranking_value.toFixed(3)}`)
      onChampionSelected()
    } catch (error) {
      toast.danger('Automatic Model Selection failed', error instanceof Error ? error.message : undefined)
    } finally {
      setBusyStep(null)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Train a champion for {marketKey}</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-5">
        <Stepper steps={STEPS} currentStepId={currentStepId} />

        <div className="flex flex-wrap items-center gap-3">
          <Button variant="secondary" size="sm" loading={busyStep === 'build'} onClick={handleBuild}>
            1. Build dataset
          </Button>
          <Button variant="secondary" size="sm" disabled={!dataset} loading={busyStep === 'validate'} onClick={handleValidate}>
            2. Validate
          </Button>
          <Button
            variant="secondary"
            size="sm"
            disabled={!dataset || dataset.status !== 'validated'}
            loading={busyStep === 'approve'}
            onClick={handleApprove}
          >
            3. Approve
          </Button>
        </div>

        {dataset && (
          <div className="flex items-center gap-2 text-xs text-text-secondary">
            <span className="font-mono">dataset v{dataset.version}</span>
            <Badge variant="neutral">{dataset.status}</Badge>
            <span>{dataset.sample_count} samples</span>
          </div>
        )}

        <div className="flex flex-wrap items-end gap-3 border-t border-border-subtle pt-4">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="model-key-prefix">Model key prefix</Label>
            <Input
              id="model-key-prefix"
              placeholder="e.g. football-1x2"
              value={modelKeyPrefix}
              onChange={(e) => setModelKeyPrefix(e.target.value)}
              className="w-56"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="target-type">Target type</Label>
            <Select value={targetType} onValueChange={(v) => setTargetType(v as typeof targetType)}>
              <SelectTrigger id="target-type" className="w-44">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="classification">Classification</SelectItem>
                <SelectItem value="regression">Regression</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <Button
            disabled={!dataset || dataset.status !== 'approved'}
            loading={busyStep === 'select-champion'}
            onClick={handleSelectChampion}
          >
            4. Select champion
          </Button>
        </div>

        {result && (
          <div className="rounded-md bg-success-muted p-3 text-sm text-success">
            Winner: <span className="font-mono">{result.algorithm}</span> ({result.framework}) —{' '}
            {result.ranking_metric} {result.ranking_value.toFixed(3)}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
