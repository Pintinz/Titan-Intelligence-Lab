import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { KeyValueGrid } from '@/components/domain/key-value-grid'
import { marketsApi } from '@/lib/api/markets'
import { predictionsApi } from '@/lib/api/predictions'
import { adminPredictionsApi } from '@/lib/api/admin-predictions'
import { queryClient } from '@/lib/query-client'
import { toast } from '@/stores/toast-store'
import { Download } from 'lucide-react'

function downloadJsonAsCsv(rows: unknown[], filename: string) {
  if (rows.length === 0 || typeof rows[0] !== 'object' || rows[0] === null) {
    toast.warning('Nothing to export', 'This market has no exportable predictions in the current window.')
    return
  }
  const columns = Object.keys(rows[0] as Record<string, unknown>)
  const csvLines = [
    columns.join(','),
    ...rows.map((row) =>
      columns
        .map((col) => {
          const value = (row as Record<string, unknown>)[col]
          const text = value === null || value === undefined ? '' : String(value)
          return `"${text.replace(/"/g, '""')}"`
        })
        .join(','),
    ),
  ]
  const blob = new Blob([csvLines.join('\n')], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

export function PredictionMarketWorkbench() {
  const [marketKey, setMarketKey] = useState<string>()
  const [rejectingId, setRejectingId] = useState<string | null>(null)
  const [rejectReason, setRejectReason] = useState('')

  const marketsQuery = useQuery({ queryKey: ['markets', 'list', 'all'], queryFn: () => marketsApi.list() })
  const markets = marketsQuery.data ?? []
  const selectedMarket = markets.find((m) => m.market_key === marketKey) ?? markets[0]
  const activeKey = marketKey ?? selectedMarket?.market_key

  const confidenceQuery = useQuery({
    queryKey: ['admin', 'predictions', 'confidence', activeKey],
    queryFn: () => adminPredictionsApi.marketConfidence(activeKey!),
    enabled: Boolean(activeKey),
  })
  const accuracyQuery = useQuery({
    queryKey: ['admin', 'predictions', 'accuracy', activeKey],
    queryFn: () => adminPredictionsApi.marketAccuracy(activeKey!),
    enabled: Boolean(activeKey),
  })
  const driftQuery = useQuery({
    queryKey: ['admin', 'predictions', 'drift', activeKey],
    queryFn: () => adminPredictionsApi.marketDrift(activeKey!),
    enabled: Boolean(activeKey),
  })
  const reviewQueueQuery = useQuery({
    queryKey: ['admin', 'predictions', 'review', selectedMarket?.id],
    queryFn: () => predictionsApi.list(selectedMarket!.id, { status: 'draft', limit: 50 }),
    enabled: Boolean(selectedMarket),
  })

  async function handleApprove(predictionId: string) {
    try {
      await predictionsApi.approve(predictionId)
      toast.success('Prediction approved', 'Published to the market.')
      void queryClient.invalidateQueries({ queryKey: ['admin', 'predictions', 'review'] })
    } catch (error) {
      toast.danger('Approval failed', error instanceof Error ? error.message : undefined)
    }
  }

  async function handleReject(predictionId: string) {
    try {
      await predictionsApi.reject(predictionId, rejectReason || undefined)
      toast.success('Prediction rejected')
      setRejectingId(null)
      setRejectReason('')
      void queryClient.invalidateQueries({ queryKey: ['admin', 'predictions', 'review'] })
    } catch (error) {
      toast.danger('Rejection failed', error instanceof Error ? error.message : undefined)
    }
  }

  async function handleExport() {
    if (!activeKey) return
    const rows = await adminPredictionsApi.exportMarket(activeKey)
    downloadJsonAsCsv(rows, `${activeKey}-predictions.csv`)
  }

  return (
    <div className="flex flex-col gap-4 lg:col-span-2">
      <div className="flex flex-wrap items-center gap-3">
        <Select value={activeKey} onValueChange={setMarketKey}>
          <SelectTrigger className="w-72">
            <SelectValue placeholder="Select a market" />
          </SelectTrigger>
          <SelectContent>
            {markets.map((market) => (
              <SelectItem key={market.id} value={market.market_key}>
                {market.name} · {market.sport_code}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button variant="secondary" size="sm" onClick={handleExport} disabled={!activeKey}>
          <Download className="h-3.5 w-3.5" aria-hidden="true" />
          Export CSV
        </Button>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle>Confidence</CardTitle>
          </CardHeader>
          <CardContent>
            <KeyValueGrid data={(confidenceQuery.data as Record<string, unknown>) ?? {}} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Accuracy</CardTitle>
          </CardHeader>
          <CardContent>
            <KeyValueGrid data={(accuracyQuery.data as Record<string, unknown>) ?? {}} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Drift</CardTitle>
          </CardHeader>
          <CardContent>
            <KeyValueGrid data={(driftQuery.data as Record<string, unknown>) ?? {}} />
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Review queue — draft predictions</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          {reviewQueueQuery.data?.length === 0 && (
            <p className="text-sm text-text-muted">No draft predictions awaiting review for this market.</p>
          )}
          {reviewQueueQuery.data?.map((prediction) => (
            <div key={prediction.id} className="flex flex-col gap-2 rounded-md border border-border-subtle p-3">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-sm text-text-primary">{prediction.subject_ref}</p>
                  <p className="font-mono text-xs text-text-muted">
                    {prediction.value} · confidence {Math.round(prediction.confidence.overall * 100)}%
                  </p>
                </div>
                <Badge variant="neutral">{prediction.status}</Badge>
              </div>
              {rejectingId === prediction.id ? (
                <div className="flex flex-col gap-2">
                  <Textarea
                    placeholder="Reason for rejection (optional)"
                    value={rejectReason}
                    onChange={(e) => setRejectReason(e.target.value)}
                  />
                  <div className="flex gap-2">
                    <Button size="sm" variant="danger" onClick={() => handleReject(prediction.id)}>
                      Confirm reject
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => setRejectingId(null)}>
                      Cancel
                    </Button>
                  </div>
                </div>
              ) : (
                <div className="flex gap-2">
                  <Button size="sm" onClick={() => handleApprove(prediction.id)}>
                    Approve
                  </Button>
                  <Button size="sm" variant="secondary" onClick={() => setRejectingId(prediction.id)}>
                    Reject
                  </Button>
                </div>
              )}
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  )
}
