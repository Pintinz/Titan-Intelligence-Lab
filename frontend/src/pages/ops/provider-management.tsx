import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { useQueryClient } from '@tanstack/react-query'
import {
  Plug,
  ChevronDown,
  ChevronRight,
  Stethoscope,
  History,
  Zap,
  Power,
  Trash2,
  KeyRound,
  PlusCircle,
  UploadCloud,
  Gauge,
  Settings2,
  Waypoints,
  Users,
} from 'lucide-react'
import { adminPlatformApi } from '@/lib/api/admin-platform'
import { sportsApi } from '@/lib/api/sports'
import { useRealtimeInvalidate } from '@/lib/hooks/use-realtime-invalidate'
import type { ProviderAuthType, ProviderCategory, ProviderDto, TeamMappingSuggestionDto } from '@/lib/api/types'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog'
import { Skeleton } from '@/components/ui/skeleton'
import { ErrorState } from '@/components/ui/error-state'
import { EmptyState } from '@/components/ui/empty-state'
import { KeyValueGrid } from '@/components/domain/key-value-grid'
import { OpsPageHeader, HealthPill, SectionCard } from '@/components/ops/ops-primitives'
import { toast } from '@/stores/toast-store'

const CATEGORIES: ProviderCategory[] = ['sports_data', 'ai', 'news', 'odds', 'general']

function statusToHealth(status: string): 'healthy' | 'warning' | 'offline' | 'unknown' {
  const s = status.toLowerCase()
  if (s === 'active' || s === 'healthy') return 'healthy'
  if (s === 'degraded' || s === 'warning') return 'warning'
  if (s === 'offline' || s === 'inactive' || s === 'disabled') return 'offline'
  return 'unknown'
}

function connectionResultTone(status: string): 'success' | 'warning' | 'danger' {
  if (status === 'healthy') return 'success'
  if (status === 'warning' || status === 'not_configured') return 'warning'
  return 'danger'
}

function CredentialsPanel({ providerId }: { providerId: string }) {
  const queryClient = useQueryClient()
  const [label, setLabel] = useState('')
  const [value, setValue] = useState('')
  const [rotateForId, setRotateForId] = useState<string | null>(null)
  const [rotateValue, setRotateValue] = useState('')

  const credentialsQuery = useQuery({
    queryKey: ['admin', 'providers', providerId, 'credentials'],
    queryFn: () => adminPlatformApi.listProviderCredentials(providerId),
  })

  const invalidate = () => void queryClient.invalidateQueries({ queryKey: ['admin', 'providers', providerId, 'credentials'] })

  const addCredential = useMutation({
    mutationFn: () => adminPlatformApi.addProviderCredential(providerId, { label, value }),
    onSuccess: () => {
      toast.success('Credential added', label)
      setLabel('')
      setValue('')
      invalidate()
    },
    onError: (error) => toast.danger('Could not add credential', error instanceof Error ? error.message : undefined),
  })

  const rotateKey = useMutation({
    mutationFn: (oldCredentialId: string) =>
      adminPlatformApi.rotateProviderKey(providerId, { old_credential_id: oldCredentialId, label: `${label || 'rotated'}`, value: rotateValue }),
    onSuccess: () => {
      toast.success('Key rotated')
      setRotateForId(null)
      setRotateValue('')
      invalidate()
    },
    onError: (error) => toast.danger('Could not rotate key', error instanceof Error ? error.message : undefined),
  })

  const credentials = credentialsQuery.data ?? []

  return (
    <div>
      <p className="mb-2 flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-text-muted">
        <KeyRound className="size-3" /> Credentials
      </p>
      {credentialsQuery.isPending && <Skeleton className="h-12" />}
      {credentialsQuery.isError && <ErrorState error={credentialsQuery.error} onRetry={() => void credentialsQuery.refetch()} />}
      {credentials.length === 0 && !credentialsQuery.isPending && <p className="text-sm text-text-muted">No credentials stored yet.</p>}
      {credentials.length > 0 && (
        <ul className="space-y-1.5">
          {credentials.map((credential) => (
            <li key={credential.id} className="rounded border border-border-subtle p-2 text-xs">
              <div className="flex items-center justify-between gap-2">
                <div className="min-w-0">
                  <p className="truncate font-mono text-text-primary">
                    {credential.label} {!credential.is_active && <span className="text-text-muted">(rotated)</span>}
                  </p>
                  <p className="font-mono text-text-muted">{credential.masked_value}</p>
                </div>
                {credential.is_active && rotateForId !== credential.id && (
                  <Button size="sm" variant="ghost" onClick={() => setRotateForId(credential.id)}>
                    Rotate
                  </Button>
                )}
              </div>
              {rotateForId === credential.id && (
                <div className="mt-2 flex gap-1.5">
                  <Input
                    placeholder="new value"
                    value={rotateValue}
                    onChange={(e) => setRotateValue(e.target.value)}
                    className="h-7 flex-1 text-xs"
                  />
                  <Button size="sm" onClick={() => rotateKey.mutate(credential.id)} disabled={!rotateValue || rotateKey.isPending}>
                    {rotateKey.isPending ? '…' : 'Save'}
                  </Button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
      <div className="mt-3 flex flex-wrap gap-1.5">
        <Input placeholder="label" value={label} onChange={(e) => setLabel(e.target.value)} className="h-8 w-24 text-xs" />
        <Input
          placeholder="credential value"
          type="password"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          className="h-8 flex-1 min-w-[120px] text-xs"
        />
        <Button size="sm" onClick={() => addCredential.mutate()} disabled={!label || !value || addCredential.isPending} className="gap-1">
          <PlusCircle className="size-3.5" /> Add
        </Button>
      </div>
    </div>
  )
}

const AUTH_TYPES: Array<{ value: ProviderAuthType | 'none'; label: string }> = [
  { value: 'none', label: 'None (unauthenticated)' },
  { value: 'bearer', label: 'Bearer token' },
  { value: 'api_key_header', label: 'API key header' },
  { value: 'api_key_query', label: 'API key query param' },
  { value: 'basic', label: 'Basic auth' },
]

/** Base URL and auth wiring for the connection tester — separate from `CredentialsPanel` below,
 * since a credential's *value* is encrypted/managed there, but nothing previously let an admin
 * tell the tester *how* to use it (which scheme, which header name a provider actually expects,
 * e.g. API-Football's `x-apisports-key` rather than a generic `X-API-Key`). Without this, a
 * correctly-added credential was silently never attached to the test request. */
function ConnectionSettingsPanel({ provider, onSaved }: { provider: ProviderDto; onSaved: () => void }) {
  const [baseUrl, setBaseUrl] = useState(provider.base_url ?? '')
  const [authType, setAuthType] = useState<ProviderAuthType | 'none'>(provider.auth_type ?? 'none')
  const [headerName, setHeaderName] = useState(provider.auth_header_name ?? '')

  const dirty =
    baseUrl !== (provider.base_url ?? '') ||
    authType !== (provider.auth_type ?? 'none') ||
    (authType === 'api_key_header' && headerName !== (provider.auth_header_name ?? ''))

  const save = useMutation({
    mutationFn: () =>
      adminPlatformApi.updateProvider(provider.id, {
        base_url: baseUrl || null,
        auth_type: authType === 'none' ? null : authType,
        auth_header_name: authType === 'api_key_header' ? headerName || null : null,
      }),
    onSuccess: () => {
      toast.success('Connection settings saved')
      onSaved()
    },
    onError: (error) => toast.danger('Could not save connection settings', error instanceof Error ? error.message : undefined),
  })

  return (
    <div>
      <p className="mb-2 flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-text-muted">
        <Settings2 className="size-3" /> Connection settings
      </p>
      <div className="space-y-2.5">
        <div>
          <Label htmlFor={`base-url-${provider.id}`}>Base URL</Label>
          <Input
            id={`base-url-${provider.id}`}
            placeholder="https://api.example.com"
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            className="mt-1.5 h-8 text-xs"
          />
        </div>
        <div>
          <Label htmlFor={`auth-type-${provider.id}`}>Auth type</Label>
          <Select value={authType} onValueChange={(v) => setAuthType(v as ProviderAuthType | 'none')}>
            <SelectTrigger id={`auth-type-${provider.id}`} className="mt-1.5 h-8 text-xs"><SelectValue /></SelectTrigger>
            <SelectContent>
              {AUTH_TYPES.map((t) => (
                <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        {authType === 'api_key_header' && (
          <div>
            <Label htmlFor={`header-name-${provider.id}`}>Header name</Label>
            <Input
              id={`header-name-${provider.id}`}
              placeholder="x-apisports-key"
              value={headerName}
              onChange={(e) => setHeaderName(e.target.value)}
              className="mt-1.5 h-8 font-mono text-xs"
            />
            <p className="mt-1 text-[11px] text-text-muted">Defaults to "X-API-Key" if left blank.</p>
          </div>
        )}
        <Button size="sm" onClick={() => save.mutate()} disabled={!dirty || save.isPending}>
          {save.isPending ? 'Saving…' : 'Save'}
        </Button>
      </div>
    </div>
  )
}

function UsagePanel({ providerId }: { providerId: string }) {
  const usageQuery = useQuery({
    queryKey: ['admin', 'providers', providerId, 'usage'],
    queryFn: () => adminPlatformApi.providerUsage(providerId, 'daily'),
  })

  return (
    <div>
      <p className="mb-2 flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-text-muted">
        <Gauge className="size-3" /> Usage (today)
      </p>
      {usageQuery.isPending && <Skeleton className="h-16" />}
      {usageQuery.isError && <ErrorState error={usageQuery.error} onRetry={() => void usageQuery.refetch()} />}
      {usageQuery.data && (
        <KeyValueGrid
          data={{
            requests_today: usageQuery.data.current_window_requests,
            quota_limit: usageQuery.data.quota_limit,
            remaining_requests: usageQuery.data.remaining_requests,
            success_rate: usageQuery.data.success_rate,
          }}
        />
      )}
    </div>
  )
}

function ProviderDetail({ provider }: { provider: ProviderDto }) {
  const providerId = provider.id
  const queryClient = useQueryClient()
  const summaryQuery = useQuery({
    queryKey: ['admin', 'providers', providerId, 'health-summary'],
    queryFn: () => adminPlatformApi.providerHealthSummary(providerId),
  })
  const trendQuery = useQuery({
    queryKey: ['admin', 'providers', providerId, 'health-trend'],
    queryFn: () => adminPlatformApi.providerHealthTrend(providerId),
  })
  const incidentsQuery = useQuery({
    queryKey: ['admin', 'providers', providerId, 'incidents'],
    queryFn: () => adminPlatformApi.providerIncidents(providerId),
  })
  const diagnosticsQuery = useQuery({
    queryKey: ['admin', 'providers', providerId, 'diagnostics'],
    queryFn: () => adminPlatformApi.providerDiagnostics(providerId),
  })

  useRealtimeInvalidate(
    'providerHealthState',
    [['admin', 'providers', providerId, 'health-summary'], ['admin', 'providers', providerId, 'health-trend']],
    `provider_id=eq.${providerId}`,
  )
  useRealtimeInvalidate('providerIncidents', [['admin', 'providers', providerId, 'incidents']], `provider_id=eq.${providerId}`)

  return (
    <div className="grid gap-4 border-t border-border-subtle p-4 sm:grid-cols-2">
      <ConnectionSettingsPanel
        provider={provider}
        onSaved={() => void queryClient.invalidateQueries({ queryKey: ['admin', 'providers'] })}
      />
      <div>
        <p className="mb-2 text-xs font-medium uppercase tracking-wide text-text-muted">Health summary (24h)</p>
        {summaryQuery.isPending && <Skeleton className="h-16" />}
        {summaryQuery.isError && <ErrorState error={summaryQuery.error} onRetry={() => void summaryQuery.refetch()} />}
        {summaryQuery.data && <KeyValueGrid data={summaryQuery.data} />}
      </div>
      <div>
        <p className="mb-2 text-xs font-medium uppercase tracking-wide text-text-muted">Diagnostics</p>
        {diagnosticsQuery.isPending && <Skeleton className="h-16" />}
        {diagnosticsQuery.isError && <ErrorState error={diagnosticsQuery.error} onRetry={() => void diagnosticsQuery.refetch()} />}
        {diagnosticsQuery.data && <KeyValueGrid data={diagnosticsQuery.data} />}
      </div>
      <div>
        <p className="mb-2 text-xs font-medium uppercase tracking-wide text-text-muted">Health trend (7d)</p>
        {trendQuery.isPending && <Skeleton className="h-16" />}
        {trendQuery.isError && <ErrorState error={trendQuery.error} onRetry={() => void trendQuery.refetch()} />}
        {trendQuery.data && trendQuery.data.length === 0 && <p className="text-sm text-text-muted">No trend data recorded yet.</p>}
        {trendQuery.data && trendQuery.data.length > 0 && (
          <ul className="space-y-1.5">
            {trendQuery.data.slice(0, 5).map((point, i) => (
              <li key={i} className="rounded border border-border-subtle p-2 text-xs">
                <KeyValueGrid data={point as Record<string, unknown>} />
              </li>
            ))}
          </ul>
        )}
      </div>
      <div>
        <p className="mb-2 flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-text-muted">
          <History className="size-3" /> Incidents
        </p>
        {incidentsQuery.isPending && <Skeleton className="h-16" />}
        {incidentsQuery.isError && <ErrorState error={incidentsQuery.error} onRetry={() => void incidentsQuery.refetch()} />}
        {incidentsQuery.data && incidentsQuery.data.length === 0 && <p className="text-sm text-text-muted">No incidents recorded.</p>}
        {incidentsQuery.data && incidentsQuery.data.length > 0 && (
          <ul className="space-y-1.5">
            {incidentsQuery.data.slice(0, 5).map((incident, i) => (
              <li key={i} className="rounded border border-danger/30 bg-danger-muted p-2 text-xs">
                <KeyValueGrid data={incident as Record<string, unknown>} />
              </li>
            ))}
          </ul>
        )}
      </div>
      <CredentialsPanel providerId={providerId} />
      <UsagePanel providerId={providerId} />
    </div>
  )
}

function RegisterProviderForm({ onRegistered }: { onRegistered: () => void }) {
  const [key, setKey] = useState('')
  const [name, setName] = useState('')
  const [category, setCategory] = useState<ProviderCategory>('sports_data')
  const [baseUrl, setBaseUrl] = useState('')

  const register = useMutation({
    mutationFn: () => adminPlatformApi.registerProvider({ key, name, category, base_url: baseUrl || null }),
    onSuccess: (provider) => {
      toast.success('Provider registered', provider.name)
      setKey('')
      setName('')
      setBaseUrl('')
      onRegistered()
    },
    onError: (error) => toast.danger('Could not register provider', error instanceof Error ? error.message : undefined),
  })

  const [envVarName, setEnvVarName] = useState('')
  const importFromEnv = useMutation({
    mutationFn: () =>
      adminPlatformApi.importProviderFromEnv({ env_var_name: envVarName, key, name: name || key, category }),
    onSuccess: ({ provider }) => {
      toast.success('Imported from .env', provider.name)
      setEnvVarName('')
      onRegistered()
    },
    onError: (error) => toast.danger('Could not import from .env', error instanceof Error ? error.message : undefined),
  })

  return (
    <SectionCard icon={PlusCircle} title="Register a provider" description="Adds a provider to the registry — inactive until activated and credentialed.">
      <div className="flex flex-wrap items-end gap-2">
        <div>
          <Label htmlFor="provider-key">Key</Label>
          <Input id="provider-key" placeholder="api_football" value={key} onChange={(e) => setKey(e.target.value)} className="mt-1.5 w-36" />
        </div>
        <div>
          <Label htmlFor="provider-name">Name</Label>
          <Input id="provider-name" placeholder="API-Football" value={name} onChange={(e) => setName(e.target.value)} className="mt-1.5 w-44" />
        </div>
        <div>
          <Label htmlFor="provider-category">Category</Label>
          <Select value={category} onValueChange={(v) => setCategory(v as ProviderCategory)}>
            <SelectTrigger id="provider-category" className="mt-1.5 w-36"><SelectValue /></SelectTrigger>
            <SelectContent>
              {CATEGORIES.map((c) => (
                <SelectItem key={c} value={c} className="capitalize">{c.replace('_', ' ')}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div>
          <Label htmlFor="provider-base-url">Base URL (optional)</Label>
          <Input
            id="provider-base-url"
            placeholder="https://api.example.com"
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            className="mt-1.5 w-56"
          />
        </div>
        <Button onClick={() => register.mutate()} disabled={!key || !name || register.isPending}>
          {register.isPending ? 'Registering…' : 'Register'}
        </Button>
      </div>

      <div className="mt-4 flex flex-wrap items-end gap-2 border-t border-border-subtle pt-4">
        <div className="min-w-0">
          <Label htmlFor="import-env-var">Import from .env instead</Label>
          <p className="mt-0.5 text-[11px] text-text-muted">
            Reads the named environment variable once and encrypts it into the registry — the key/name/category above are reused.
          </p>
        </div>
        <Input
          id="import-env-var"
          placeholder="TITANIQ_API_FOOTBALL_KEY"
          value={envVarName}
          onChange={(e) => setEnvVarName(e.target.value)}
          className="w-64 font-mono text-xs"
        />
        <Button
          variant="secondary"
          onClick={() => importFromEnv.mutate()}
          disabled={!envVarName || !key || importFromEnv.isPending}
          className="gap-1"
        >
          <UploadCloud className="size-3.5" /> {importFromEnv.isPending ? 'Importing…' : 'Import'}
        </Button>
      </div>
    </SectionCard>
  )
}

/** Owns its own test/activate/disable mutations, scoped to this one provider — previously these
 * three mutations lived once at the page level and were shared across every provider row, so
 * testing (or activating/disabling) one provider set a *global* pending/error state that every
 * other row's button read from too: testing Gemini disabled the API-Football row's button, and
 * clicking a second provider's button while the first request was still in flight could resolve
 * out of order and surface the wrong provider's result. */
function ProviderRow({
  provider,
  isExpanded,
  onToggleExpand,
  onRequestDelete,
  deletePending,
  onMutated,
}: {
  provider: ProviderDto
  isExpanded: boolean
  onToggleExpand: () => void
  onRequestDelete: () => void
  deletePending: boolean
  onMutated: () => void
}) {
  const queryClient = useQueryClient()

  const activate = useMutation({
    mutationFn: () => adminPlatformApi.activateProvider(provider.id),
    onSuccess: onMutated,
    onError: (error) => toast.danger('Could not activate provider', error instanceof Error ? error.message : undefined),
  })

  const disable = useMutation({
    mutationFn: () => adminPlatformApi.disableProvider(provider.id),
    onSuccess: onMutated,
    onError: (error) => toast.danger('Could not disable provider', error instanceof Error ? error.message : undefined),
  })

  const testConnection = useMutation({
    mutationFn: () => adminPlatformApi.testProviderConnection(provider.id),
    onSuccess: (result) => {
      toast[connectionResultTone(result.status)](`${provider.name}: ${result.status.replace('_', ' ')}`, result.message)
      void queryClient.invalidateQueries({ queryKey: ['admin', 'providers', provider.id] })
    },
    onError: (error) =>
      toast.danger(`Could not test ${provider.name}`, error instanceof Error ? error.message : undefined),
  })

  return (
    <Card className="overflow-hidden">
      <div
        role="button"
        tabIndex={0}
        onClick={onToggleExpand}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault()
            onToggleExpand()
          }
        }}
        className="flex w-full cursor-pointer items-center gap-3 p-4 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary"
        aria-expanded={isExpanded}
      >
        {isExpanded ? (
          <ChevronDown className="size-4 shrink-0 text-text-muted" aria-hidden="true" />
        ) : (
          <ChevronRight className="size-4 shrink-0 text-text-muted" aria-hidden="true" />
        )}
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <p className="font-display text-sm font-semibold text-text-primary">{provider.name}</p>
            <HealthPill status={statusToHealth(provider.status)} />
          </div>
          <p className="font-mono text-xs text-text-muted">
            {provider.key} · {provider.category} · priority {provider.priority}
            {provider.base_url && ` · ${provider.base_url}`}
          </p>
          {provider.capability_note && (
            <p className="mt-1 text-xs text-warning">{provider.capability_note}</p>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-2" onClick={(e) => e.stopPropagation()}>
          <Button
            size="sm"
            variant="secondary"
            onClick={() => testConnection.mutate()}
            disabled={testConnection.isPending}
            className="gap-1"
          >
            <Stethoscope className="size-3.5" />
            {testConnection.isPending ? 'Testing…' : 'Test connection'}
          </Button>
          {provider.status === 'active' ? (
            <Button size="sm" variant="secondary" onClick={() => disable.mutate()} disabled={disable.isPending} className="gap-1">
              <Power className="size-3.5" />
              {disable.isPending ? 'Disabling…' : 'Disable'}
            </Button>
          ) : (
            <Button size="sm" onClick={() => activate.mutate()} disabled={activate.isPending} className="gap-1">
              <Zap className="size-3.5" />
              {activate.isPending ? 'Activating…' : 'Activate'}
            </Button>
          )}
          <Button size="icon" variant="ghost" aria-label="Delete provider" onClick={onRequestDelete} disabled={deletePending}>
            <Trash2 className="size-3.5 text-danger" />
          </Button>
        </div>
      </div>
      {isExpanded && <ProviderDetail provider={provider} />}
    </Card>
  )
}

/** football-data.org is currently the only alternate provider a competition can be routed to
 * for upcoming fixtures — SportsProviderRouter.fixture_schedule_adapters has exactly one entry.
 * Hardcoded here rather than fetched, matching that reality; add a real selector if/when a
 * second alternate fixture-schedule provider is ever wired up. */
const FIXTURE_SOURCE_PROVIDER_KEY = 'football_data_org'

function TeamMappingDialog({
  open,
  onOpenChange,
  competitionId,
  providerCompetitionRef,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  competitionId: string
  providerCompetitionRef: string
}) {
  const [confirmed, setConfirmed] = useState<Record<string, string>>({}) // fd team id -> titaniq team id

  const suggestionsQuery = useQuery({
    queryKey: ['admin', 'football-data-org', 'team-suggestions', competitionId, providerCompetitionRef],
    queryFn: () => adminPlatformApi.suggestTeamMappings(competitionId, providerCompetitionRef),
    enabled: open && !!providerCompetitionRef,
  })

  const confirm = useMutation({
    mutationFn: () =>
      adminPlatformApi.confirmTeamMappings(
        Object.entries(confirmed).map(([football_data_org_team_id, titaniq_team_id]) => ({
          football_data_org_team_id,
          titaniq_team_id,
        })),
      ),
    onSuccess: (result) => {
      toast.success('Team mappings confirmed', `${result.mapped} team${result.mapped === 1 ? '' : 's'} mapped`)
      onOpenChange(false)
    },
    onError: (error) => toast.danger('Could not confirm mappings', error instanceof Error ? error.message : undefined),
  })

  function toggle(suggestion: TeamMappingSuggestionDto) {
    setConfirmed((prev) => {
      const next = { ...prev }
      if (next[suggestion.football_data_org_team_id]) {
        delete next[suggestion.football_data_org_team_id]
      } else if (suggestion.suggested_titaniq_team_id) {
        next[suggestion.football_data_org_team_id] = suggestion.suggested_titaniq_team_id
      }
      return next
    })
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Map football-data.org teams</DialogTitle>
          <DialogDescription>
            Suggested by name match against TitanIQ's existing teams — review before confirming. Nothing is written
            until you confirm.
          </DialogDescription>
        </DialogHeader>

        {suggestionsQuery.isPending && <Skeleton className="h-32" />}
        {suggestionsQuery.isError && (
          <ErrorState error={suggestionsQuery.error} onRetry={() => void suggestionsQuery.refetch()} />
        )}
        {suggestionsQuery.data && suggestionsQuery.data.length === 0 && (
          <p className="text-xs text-text-muted">football-data.org returned no teams for this competition ref.</p>
        )}
        {suggestionsQuery.data && suggestionsQuery.data.length > 0 && (
          <ul className="max-h-80 space-y-1.5 overflow-y-auto">
            {suggestionsQuery.data.map((s) => (
              <li
                key={s.football_data_org_team_id}
                className="flex items-center justify-between gap-2 rounded border border-border-subtle px-2.5 py-1.5 text-xs"
              >
                <span className="min-w-0 truncate">{s.football_data_org_team_name}</span>
                <span className="text-text-muted">→</span>
                {s.suggested_titaniq_team_id ? (
                  <label className="flex min-w-0 items-center gap-1.5">
                    <input
                      type="checkbox"
                      checked={!!confirmed[s.football_data_org_team_id]}
                      onChange={() => toggle(s)}
                    />
                    <span className="truncate">{s.suggested_titaniq_team_name}</span>
                  </label>
                ) : (
                  <span className="italic text-text-muted">no match found</span>
                )}
              </li>
            ))}
          </ul>
        )}

        <DialogFooter>
          <Button variant="secondary" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={() => confirm.mutate()} disabled={Object.keys(confirmed).length === 0 || confirm.isPending}>
            {confirm.isPending ? 'Confirming…' : `Confirm ${Object.keys(confirmed).length} mapping${Object.keys(confirmed).length === 1 ? '' : 's'}`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function CompetitionFixtureSourceSection() {
  const queryClient = useQueryClient()
  const [competitionId, setCompetitionId] = useState('')
  const [providerRef, setProviderRef] = useState('')
  const [notes, setNotes] = useState('')
  const [seasonLabel, setSeasonLabel] = useState('')
  const [seasonId, setSeasonId] = useState('')
  const [mappingOpen, setMappingOpen] = useState(false)

  const competitionsQuery = useQuery({
    queryKey: ['sports', 'competitions', 'football'],
    queryFn: () => sportsApi.listCompetitions('football'),
  })

  const preferenceQuery = useQuery({
    queryKey: ['admin', 'competitions', competitionId, 'fixture-source'],
    queryFn: () => adminPlatformApi.getCompetitionFixtureSource(competitionId),
    enabled: !!competitionId,
  })

  const invalidatePreference = () =>
    void queryClient.invalidateQueries({ queryKey: ['admin', 'competitions', competitionId, 'fixture-source'] })

  const save = useMutation({
    mutationFn: () =>
      adminPlatformApi.setCompetitionFixtureSource(competitionId, {
        preferred_provider_key: FIXTURE_SOURCE_PROVIDER_KEY,
        provider_competition_ref: providerRef,
        notes: notes || null,
      }),
    onSuccess: () => {
      toast.success('Fixture source saved')
      invalidatePreference()
    },
    onError: (error) => toast.danger('Could not save fixture source', error instanceof Error ? error.message : undefined),
  })

  const clear = useMutation({
    mutationFn: () => adminPlatformApi.clearCompetitionFixtureSource(competitionId),
    onSuccess: () => {
      toast.success('Fixture source cleared — back to the default provider')
      invalidatePreference()
    },
    onError: (error) => toast.danger('Could not clear fixture source', error instanceof Error ? error.message : undefined),
  })

  const triggerSync = useMutation({
    mutationFn: () =>
      adminPlatformApi.triggerUpcomingFixturesSync('football', competitionId, {
        season_label: seasonLabel,
        season_id: seasonId,
      }),
    onSuccess: (run) => {
      if (!run) {
        toast.success('Sync skipped', 'Already synced recently — use force if you need it sooner')
        return
      }
      toast.success('Upcoming fixtures synced', `${run.records_fetched} fetched, ${run.records_created} created, ${run.records_updated} updated`)
    },
    onError: (error) => toast.danger('Sync failed', error instanceof Error ? error.message : undefined),
  })

  const preference = preferenceQuery.data
  const competitions = competitionsQuery.data ?? []

  return (
    <SectionCard
      icon={Waypoints}
      title="Competition fixture sources"
      description="Route a competition's upcoming-fixture syncing to an alternate provider (currently: football-data.org) instead of the default. Results/statistics always keep using the default provider."
    >
      <div className="flex flex-wrap items-end gap-2">
        <div className="min-w-[14rem]">
          <Label htmlFor="fixture-source-competition">Competition</Label>
          <Select value={competitionId} onValueChange={setCompetitionId}>
            <SelectTrigger id="fixture-source-competition" className="mt-1.5">
              <SelectValue placeholder="Select a football competition" />
            </SelectTrigger>
            <SelectContent>
              {competitions.map((c) => (
                <SelectItem key={c.id} value={c.id}>
                  {c.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {!competitionId && competitionsQuery.data && competitions.length === 0 && (
        <p className="mt-3 text-xs text-text-muted">
          No football competitions under coverage yet — bootstrap one first (Data Pipeline).
        </p>
      )}

      {competitionId && (
        <div className="mt-4 space-y-4 border-t border-border-subtle pt-4">
          {preferenceQuery.isPending && <Skeleton className="h-8" />}

          {preference && (
            <div className="flex flex-wrap items-center justify-between gap-2 rounded border border-border-default bg-bg-elevated px-3 py-2 text-xs">
              <span>
                Currently routed to <span className="font-medium">{preference.preferred_provider_key}</span> using ref{' '}
                <span className="font-mono">{preference.provider_competition_ref}</span>
                {preference.notes && <span className="text-text-muted"> — {preference.notes}</span>}
              </span>
              <Button variant="secondary" size="sm" onClick={() => clear.mutate()} disabled={clear.isPending}>
                {clear.isPending ? 'Clearing…' : 'Clear'}
              </Button>
            </div>
          )}

          {!preference && !preferenceQuery.isPending && (
            <p className="text-xs text-text-muted">No preference set — this competition uses the default provider.</p>
          )}

          <div className="flex flex-wrap items-end gap-2">
            <div>
              <Label htmlFor="fixture-source-ref">football-data.org competition ref</Label>
              <Input
                id="fixture-source-ref"
                placeholder="PL"
                value={providerRef}
                onChange={(e) => setProviderRef(e.target.value)}
                className="mt-1.5 w-28"
              />
            </div>
            <div className="min-w-[16rem] flex-1">
              <Label htmlFor="fixture-source-notes">Notes (optional)</Label>
              <Input
                id="fixture-source-notes"
                placeholder="Why this competition uses football-data.org"
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                className="mt-1.5"
              />
            </div>
            <Button onClick={() => save.mutate()} disabled={!providerRef || save.isPending}>
              {save.isPending ? 'Saving…' : 'Save'}
            </Button>
            <Button variant="secondary" onClick={() => setMappingOpen(true)} disabled={!providerRef} className="gap-1">
              <Users className="size-3.5" /> Map teams
            </Button>
          </div>

          <div className="flex flex-wrap items-end gap-2 border-t border-border-subtle pt-4">
            <div>
              <Label htmlFor="fixture-source-season-label">Season label</Label>
              <Input
                id="fixture-source-season-label"
                placeholder="2026"
                value={seasonLabel}
                onChange={(e) => setSeasonLabel(e.target.value)}
                className="mt-1.5 w-28"
              />
            </div>
            <div>
              <Label htmlFor="fixture-source-season-id">Season id</Label>
              <Input
                id="fixture-source-season-id"
                placeholder="from bootstrap"
                value={seasonId}
                onChange={(e) => setSeasonId(e.target.value)}
                className="mt-1.5 w-56 font-mono text-xs"
              />
            </div>
            <Button
              variant="secondary"
              onClick={() => triggerSync.mutate()}
              disabled={!preference || !seasonLabel || !seasonId || triggerSync.isPending}
              className="gap-1"
            >
              <Zap className="size-3.5" /> {triggerSync.isPending ? 'Syncing…' : 'Sync upcoming fixtures now'}
            </Button>
          </div>
        </div>
      )}

      <TeamMappingDialog
        open={mappingOpen}
        onOpenChange={setMappingOpen}
        competitionId={competitionId}
        providerCompetitionRef={providerRef}
      />
    </SectionCard>
  )
}

export default function ProviderManagement() {
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<ProviderDto | null>(null)

  const providersQuery = useQuery({
    queryKey: ['admin', 'providers'],
    queryFn: () => adminPlatformApi.listProviders(),
  })

  const deleteProvider = useMutation({
    mutationFn: (providerId: string) => adminPlatformApi.deleteProvider(providerId),
    onSuccess: () => {
      toast.success('Provider deleted')
      setDeleteTarget(null)
      void providersQuery.refetch()
    },
    onError: (error) => toast.danger('Could not delete provider', error instanceof Error ? error.message : undefined),
  })

  const providers = providersQuery.data ?? []

  return (
    <div className="space-y-6">
      <OpsPageHeader
        eyebrow="Providers"
        title="Provider Management"
        description="External data providers — sports feeds, odds, news, and AI services. Register providers, manage credentials, test connections, and inspect health history."
      />

      <RegisterProviderForm onRegistered={() => void providersQuery.refetch()} />

      {providersQuery.isPending && (
        <div className="grid gap-4 sm:grid-cols-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-32" />
          ))}
        </div>
      )}

      {providersQuery.isError && <ErrorState error={providersQuery.error} onRetry={() => void providersQuery.refetch()} />}

      {providers.length === 0 && !providersQuery.isPending && (
        <EmptyState
          icon={Plug}
          title="No providers configured"
          description="Register one above — sports, news, odds, and AI providers all connect through this console."
        />
      )}

      {providers.length > 0 && (
        <div className="space-y-3">
          {providers.map((provider) => (
            <ProviderRow
              key={provider.id}
              provider={provider}
              isExpanded={expandedId === provider.id}
              onToggleExpand={() => setExpandedId(expandedId === provider.id ? null : provider.id)}
              onRequestDelete={() => setDeleteTarget(provider)}
              deletePending={deleteProvider.isPending}
              onMutated={() => void providersQuery.refetch()}
            />
          ))}
        </div>
      )}

      <CompetitionFixtureSourceSection />

      <Dialog open={!!deleteTarget} onOpenChange={(open) => !open && setDeleteTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete provider "{deleteTarget?.name}"?</DialogTitle>
            <DialogDescription>This removes its credentials and history. This cannot be undone.</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="secondary" onClick={() => setDeleteTarget(null)} disabled={deleteProvider.isPending}>
              Cancel
            </Button>
            <Button
              variant="danger"
              onClick={() => deleteTarget && deleteProvider.mutate(deleteTarget.id)}
              disabled={deleteProvider.isPending}
            >
              {deleteProvider.isPending ? 'Deleting…' : 'Delete provider'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
