import { useState } from 'react'
import { ChevronDown, CircleCheck } from 'lucide-react'
import { CDPanel, CDLabel } from './primitives/panel'
import { PredictionAccessIndicator } from './prediction-access-gate'
import type { PredictionMarketDto } from '@/lib/api/types'

/** Real backend `PredictionMarketDto.category` values (market_seeding.py) mapped to display
 * names — no invented taxonomy, this groups markets by the same category the catalog already
 * assigns them. A category absent from the fixture's real markets never renders an empty group. */
const CATEGORY_LABELS: Record<string, string> = {
  winner: 'Match Result',
  goals: 'Goals',
  totals: 'Total Goals',
  team_totals: 'Team Goals',
  score: 'Correct Score',
  clean_sheet: 'Clean Sheets',
  win_to_nil: 'Win To Nil',
  segment_winner: 'Halves',
}

function groupByCategory(markets: PredictionMarketDto[]): Array<[string, PredictionMarketDto[]]> {
  const groups = new Map<string, PredictionMarketDto[]>()
  for (const market of markets) {
    const list = groups.get(market.category) ?? []
    list.push(market)
    groups.set(market.category, list)
  }
  // Stable, deliberate order — the market a user most often wants first.
  const order = ['winner', 'goals', 'totals', 'team_totals', 'score', 'clean_sheet', 'win_to_nil', 'segment_winner']
  return order.filter((key) => groups.has(key)).map((key) => [key, groups.get(key)!])
}

/**
 * PredictionLaboratory — real markets grouped by their real catalog category, each an
 * expandable instrument bank rather than a flat wall of buttons. Selecting a market arms it;
 * Generate Intelligence only unlocks once something is armed, per the approved brief.
 */
export function PredictionLaboratory({
  markets,
  selectedMarketKey,
  onSelect,
  onGenerate,
  generating,
  hasGenerated,
}: {
  markets: PredictionMarketDto[]
  selectedMarketKey: string | null
  onSelect: (marketKey: string) => void
  onGenerate: () => void
  generating: boolean
  hasGenerated: boolean
}) {
  const groups = groupByCategory(markets)
  const [openCategory, setOpenCategory] = useState<string | null>(groups[0]?.[0] ?? null)
  const selectedMarket = markets.find((m) => m.market_key === selectedMarketKey)

  return (
    <CDPanel>
      <div className="flex items-center justify-between gap-3">
        <CDLabel>Prediction Laboratory</CDLabel>
        <span className="font-[var(--cd-font-tabular)] text-[11px] tabular-nums" style={{ color: 'var(--cd-text-muted)' }}>
          {markets.length} instrument{markets.length === 1 ? '' : 's'}
        </span>
      </div>
      <p className="mt-2 font-[var(--cd-font-body)] text-[13px]" style={{ color: 'var(--cd-text-secondary)' }}>
        Pick what you want intelligence on. Each market is a real trained instrument — nothing publishes below its own confidence threshold.
      </p>

      <div className="mt-4 space-y-2">
        {groups.map(([category, categoryMarkets]) => {
          const isOpen = openCategory === category
          const hasSelection = categoryMarkets.some((m) => m.market_key === selectedMarketKey)
          return (
            <div key={category} className="overflow-hidden rounded-[var(--cd-radius-md)] border" style={{ borderColor: 'var(--cd-border-hairline)' }}>
              <button
                type="button"
                onClick={() => setOpenCategory(isOpen ? null : category)}
                className="flex w-full items-center justify-between gap-2 px-3.5 py-2.5 transition-colors duration-[var(--cd-motion-base)]"
                style={{ backgroundColor: isOpen || hasSelection ? 'var(--cd-surface-2)' : 'transparent' }}
                aria-expanded={isOpen}
              >
                <span className="flex items-center gap-2">
                  <span className="font-[var(--cd-font-display)] text-[13px] font-semibold" style={{ color: 'var(--cd-text-primary)' }}>
                    {CATEGORY_LABELS[category] ?? category}
                  </span>
                  <span className="font-[var(--cd-font-tabular)] text-[11px] tabular-nums" style={{ color: 'var(--cd-text-muted)' }}>
                    {categoryMarkets.length}
                  </span>
                  {hasSelection && <CircleCheck className="size-3.5" style={{ color: 'var(--cd-accent)' }} aria-hidden="true" />}
                </span>
                <ChevronDown
                  className="size-4 shrink-0 transition-transform duration-[var(--cd-motion-base)]"
                  style={{ color: 'var(--cd-text-muted)', transform: isOpen ? 'rotate(180deg)' : undefined }}
                  aria-hidden="true"
                />
              </button>
              {isOpen && (
                <div className="grid gap-2 p-3 pt-1 sm:grid-cols-2">
                  {categoryMarkets.map((market) => (
                    <MarketInstrument
                      key={market.id}
                      market={market}
                      selected={selectedMarketKey === market.market_key}
                      onSelect={() => onSelect(market.market_key)}
                    />
                  ))}
                </div>
              )}
            </div>
          )
        })}
      </div>

      {selectedMarket && !hasGenerated && (
        <div className="mt-4 flex flex-wrap items-center gap-x-3 gap-y-1.5">
          <button
            type="button"
            onClick={onGenerate}
            disabled={generating}
            className="inline-flex items-center gap-2 rounded-[var(--cd-radius-md)] px-4 py-2.5 font-[var(--cd-font-body)] text-[13px] font-semibold transition-[opacity,transform] duration-[var(--cd-motion-base)] disabled:cursor-wait disabled:opacity-70"
            style={{ backgroundColor: 'var(--cd-accent)', color: 'var(--cd-text-inverse)' }}
          >
            {generating ? 'Analyzing…' : `Generate Intelligence — ${selectedMarket.name}`}
          </button>
          <PredictionAccessIndicator />
        </div>
      )}
    </CDPanel>
  )
}

function MarketInstrument({ market, selected, onSelect }: { market: PredictionMarketDto; selected: boolean; onSelect: () => void }) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className="rounded-[var(--cd-radius-md)] border p-3 text-left transition-colors duration-[var(--cd-motion-base)]"
      style={{
        borderColor: selected ? 'var(--cd-accent)' : 'var(--cd-border-default)',
        backgroundColor: selected ? 'var(--cd-accent-muted)' : 'transparent',
      }}
      aria-pressed={selected}
    >
      <p className="font-[var(--cd-font-display)] text-[13px] font-semibold" style={{ color: 'var(--cd-text-primary)' }}>
        {market.name}
      </p>
      <p className="mt-1 font-[var(--cd-font-body)] text-[12px] leading-snug" style={{ color: 'var(--cd-text-secondary)' }}>
        {market.description}
      </p>
      <p className="mt-1.5 font-[var(--cd-font-tabular)] text-[10px] tabular-nums" style={{ color: 'var(--cd-text-muted)' }}>
        ≥{Math.round(market.confidence_threshold * 100)}% confidence to publish
      </p>
    </button>
  )
}
