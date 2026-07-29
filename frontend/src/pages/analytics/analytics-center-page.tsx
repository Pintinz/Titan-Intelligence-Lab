import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Breadcrumbs } from '@/components/ui/breadcrumbs'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { StatCard } from '@/components/domain/stat-card'
import { KeyValueGrid } from '@/components/domain/key-value-grid'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { marketsApi } from '@/lib/api/markets'
import { predictionsApi } from '@/lib/api/predictions'
import { graphApi } from '@/lib/api/graph'
import { intelligenceApi } from '@/lib/api/intelligence'

export default function AnalyticsCenterPage() {
  const [marketKey, setMarketKey] = useState<string | undefined>()

  const marketsQuery = useQuery({ queryKey: ['markets', 'list'], queryFn: () => marketsApi.list({ status: 'production' }) })
  const activeMarketKey = marketKey ?? marketsQuery.data?.[0]?.market_key

  const statisticsQuery = useQuery({
    queryKey: ['predictions', 'statistics', activeMarketKey],
    queryFn: () => predictionsApi.statistics(activeMarketKey!),
    enabled: Boolean(activeMarketKey),
  })
  const monitoringQuery = useQuery({ queryKey: ['predictions', 'monitoring'], queryFn: () => predictionsApi.monitoringSummary() })
  const graphStatsQuery = useQuery({ queryKey: ['graph', 'statistics'], queryFn: () => graphApi.statistics() })
  const intelligenceStatsQuery = useQuery({ queryKey: ['intelligence', 'analytics'], queryFn: () => intelligenceApi.analytics() })

  const stats = statisticsQuery.data as Record<string, unknown> | undefined
  const monitoring = monitoringQuery.data as Record<string, unknown> | undefined

  return (
    <div className="flex flex-col gap-6 p-6">
      <div>
        <Breadcrumbs items={[{ label: 'Dashboard', to: '/app' }, { label: 'Analytics Center' }]} />
        <h1 className="mt-2 font-display text-2xl font-semibold text-text-primary">Analytics Center</h1>
      </div>

      <Select value={activeMarketKey} onValueChange={setMarketKey}>
        <SelectTrigger className="w-72">
          <SelectValue placeholder="Select a market" />
        </SelectTrigger>
        <SelectContent>
          {marketsQuery.data?.map((market) => (
            <SelectItem key={market.id} value={market.market_key}>
              {market.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Sample size" value={String(stats?.sample_size ?? '—')} />
        <StatCard
          label="Avg. probability"
          value={typeof stats?.average_probability === 'number' ? `${Math.round(stats.average_probability * 100)}%` : '—'}
        />
        <StatCard
          label="Avg. confidence"
          value={typeof stats?.average_confidence === 'number' ? `${Math.round(stats.average_confidence * 100)}%` : '—'}
        />
        <StatCard
          label="Publish rate"
          value={typeof stats?.publish_rate === 'number' ? `${Math.round(stats.publish_rate * 100)}%` : '—'}
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Prediction monitoring</CardTitle>
          </CardHeader>
          <CardContent>
            <KeyValueGrid data={monitoring ?? {}} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Knowledge Graph statistics</CardTitle>
          </CardHeader>
          <CardContent>
            <KeyValueGrid data={(graphStatsQuery.data as Record<string, unknown>) ?? {}} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Intelligence analytics</CardTitle>
          </CardHeader>
          <CardContent>
            <KeyValueGrid data={(intelligenceStatsQuery.data as Record<string, unknown>) ?? {}} />
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
