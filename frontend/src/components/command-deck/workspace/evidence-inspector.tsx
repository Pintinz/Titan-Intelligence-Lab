import { useQuery } from '@tanstack/react-query'
import { X } from 'lucide-react'
import { predictionsApi } from '@/lib/api/predictions'
import { ErrorState } from '@/components/ui/error-state'
import { GeneratedIntelligencePanel } from '../generated-intelligence'
import type { TeamRef } from '@/components/infinity/evidence-explorer'
import type { PredictionMarketDto } from '@/lib/api/types'

const UNKNOWN_TEAM: TeamRef = { name: 'Home', logoUrl: null }
const UNKNOWN_AWAY_TEAM: TeamRef = { name: 'Away', logoUrl: null }

/**
 * EvidenceInspector — the Intelligence Workspace's slide-over, opened whenever a prediction is
 * focused from any tab. Reuses `GeneratedIntelligencePanel` verbatim (the same Command-Deck-native
 * confidence/evidence rendering already shipped on Match Intelligence) rather than reimplementing
 * evidence logic — the shaped brief's "reuse existing Evidence Explorer, never rebuild logic"
 * applied literally: this ports the same component into a new shell, it doesn't duplicate it.
 */
export function EvidenceInspector({
  predictionId,
  markets,
  homeTeam,
  awayTeam,
  onClose,
}: {
  predictionId: string | null
  markets: PredictionMarketDto[]
  homeTeam?: TeamRef
  awayTeam?: TeamRef
  onClose: () => void
}) {
  const query = useQuery({
    queryKey: ['predictions', predictionId],
    queryFn: () => predictionsApi.get(predictionId!),
    enabled: !!predictionId,
  })

  const open = !!predictionId
  const marketName = query.data ? (markets.find((m) => m.id === query.data!.market_id)?.name ?? 'Prediction') : null

  return (
    <>
      <div
        className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm transition-opacity duration-[var(--cd-motion-base)]"
        style={{ opacity: open ? 1 : 0, pointerEvents: open ? 'auto' : 'none' }}
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Evidence Inspector"
        className="fixed inset-y-0 right-0 z-50 flex w-full max-w-md flex-col overflow-y-auto border-l p-5 shadow-2xl transition-transform duration-[var(--cd-motion-deliberate)] ease-out sm:p-6"
        style={{
          borderColor: 'var(--cd-border-default)',
          backgroundColor: 'var(--cd-surface-1)',
          transform: open ? 'translateX(0)' : 'translateX(100%)',
        }}
      >
        <div className="mb-4 flex items-center justify-between gap-3">
          <p className="font-[var(--cd-font-telemetry)] text-[11px] font-semibold uppercase tracking-[0.08em]" style={{ color: 'var(--cd-text-muted)' }}>
            Evidence Inspector
          </p>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close evidence inspector"
            className="rounded-[var(--cd-radius-sm)] p-1"
            style={{ color: 'var(--cd-text-muted)' }}
          >
            <X className="size-4" aria-hidden="true" />
          </button>
        </div>

        {query.isPending && open && (
          <div className="space-y-2">
            <p className="font-[var(--cd-font-telemetry)] text-[10.5px] uppercase tracking-[0.06em]" style={{ color: 'var(--cd-text-muted)' }}>
              Retrieving evidence…
            </p>
            <div className="h-40 animate-pulse rounded-[var(--cd-radius-lg)] motion-reduce:animate-none" style={{ backgroundColor: 'var(--cd-surface-2)' }} />
          </div>
        )}
        {query.isError && open && <ErrorState error={query.error} onRetry={() => void query.refetch()} />}
        {query.data && (
          <GeneratedIntelligencePanel
            marketName={marketName}
            prediction={query.data}
            isGenerating={false}
            error={null}
            homeTeam={homeTeam ?? UNKNOWN_TEAM}
            awayTeam={awayTeam ?? UNKNOWN_AWAY_TEAM}
          />
        )}
      </div>
    </>
  )
}
