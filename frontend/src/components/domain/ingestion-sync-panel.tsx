import { useState, type FormEvent } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { KeyValueGrid } from '@/components/domain/key-value-grid'
import { adminPlatformApi } from '@/lib/api/admin-platform'
import { queryClient } from '@/lib/query-client'
import { toast } from '@/stores/toast-store'

const SPORT_CODES = ['football', 'basketball', 'baseball', 'table_tennis']

export function IngestionSyncPanel() {
  const [sportCode, setSportCode] = useState(SPORT_CODES[0])
  const [competitionRef, setCompetitionRef] = useState('')
  const [triggering, setTriggering] = useState<string | null>(null)

  const statsQuery = useQuery({
    queryKey: ['admin', 'syncStats', sportCode],
    queryFn: () => adminPlatformApi.syncStats({ sport_code: sportCode, limit: 20 }),
  })
  const qualityQuery = useQuery({
    queryKey: ['admin', 'ingestionQuality', sportCode, 'teams'],
    queryFn: () => adminPlatformApi.ingestionQuality(sportCode, 'teams'),
    retry: false,
  })

  async function runTrigger(name: string, action: () => Promise<unknown>) {
    setTriggering(name)
    try {
      await action()
      toast.success(`${name} sync triggered`)
      void queryClient.invalidateQueries({ queryKey: ['admin', 'syncStatus'] })
      void queryClient.invalidateQueries({ queryKey: ['admin', 'syncStats'] })
    } catch (error) {
      toast.danger(`${name} sync failed`, error instanceof Error ? error.message : undefined)
    } finally {
      setTriggering(null)
    }
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
  }

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader>
          <CardTitle>Trigger a sync</CardTitle>
        </CardHeader>
        <CardContent>
          <form className="flex flex-wrap items-end gap-3" noValidate onSubmit={handleSubmit}>
            <div className="flex flex-col gap-1">
              <Label htmlFor="sync-sport">Sport</Label>
              <Select value={sportCode} onValueChange={setSportCode}>
                <SelectTrigger id="sync-sport" className="w-48">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {SPORT_CODES.map((code) => (
                    <SelectItem key={code} value={code}>
                      {code}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="sync-competition">Competition ref (for teams/fixtures/standings)</Label>
              <Input id="sync-competition" value={competitionRef} onChange={(e) => setCompetitionRef(e.target.value)} />
            </div>
            <Button
              type="button"
              size="sm"
              variant="secondary"
              loading={triggering === 'Countries'}
              onClick={() => runTrigger('Countries', () => adminPlatformApi.triggerSyncCountries(sportCode))}
            >
              Sync countries
            </Button>
            <Button
              type="button"
              size="sm"
              variant="secondary"
              disabled={!competitionRef}
              loading={triggering === 'Teams'}
              onClick={() => runTrigger('Teams', () => adminPlatformApi.triggerSyncTeams(sportCode, competitionRef))}
            >
              Sync teams
            </Button>
          </form>
        </CardContent>
      </Card>

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Sync stats — {sportCode}</CardTitle>
          </CardHeader>
          <CardContent>
            <KeyValueGrid data={(statsQuery.data as Record<string, unknown>) ?? {}} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Ingestion quality — {sportCode} teams</CardTitle>
          </CardHeader>
          <CardContent>
            {qualityQuery.data ? (
              <KeyValueGrid data={qualityQuery.data as Record<string, unknown>} />
            ) : (
              <p className="text-sm text-text-muted">No quality report recorded for this sport/entity yet.</p>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
