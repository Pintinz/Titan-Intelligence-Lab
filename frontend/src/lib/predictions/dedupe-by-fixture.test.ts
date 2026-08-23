import { describe, expect, it } from 'vitest'
import { dedupeByFixture, rankPicks } from './dedupe-by-fixture'
import type { PredictionPickDto } from '@/lib/api/types'

function pick(overrides: Partial<PredictionPickDto> & { id: string; subject_ref: string; confidence_composite: number }): PredictionPickDto {
  return {
    market_id: 'market-1',
    model_id: 'model-1',
    value: 'HOME_WIN',
    probability: 0.5,
    status: 'published',
    generated_at: '2026-08-23T00:00:00Z',
    market_key: 'football.match_winner',
    market_name: 'Match Winner',
    sport_code: 'football',
    evidence_count: 3,
    ai_explanation: null,
    ...overrides,
  }
}

describe('dedupeByFixture', () => {
  it('keeps only the first (highest-confidence, since input is pre-sorted) pick per subject_ref', () => {
    const picks = [
      pick({ id: 'a1', subject_ref: 'fixture-1', confidence_composite: 0.7 }),
      pick({ id: 'a2', subject_ref: 'fixture-1', confidence_composite: 0.4 }),
      pick({ id: 'b1', subject_ref: 'fixture-2', confidence_composite: 0.5 }),
    ]

    const result = dedupeByFixture(picks)

    expect(result.map((p) => p.id)).toEqual(['a1', 'b1'])
  })
})

describe('rankPicks', () => {
  it('sorts by confidence descending after deduping, with NO confidence floor', () => {
    // Live bug (2026-08-23): rankPicks used to filter out anything below AI_PICK_CONFIDENCE_FLOOR
    // (0.65) — the "AI Picks" curated-feed threshold — so Intelligence Now/Priority Intelligence
    // went completely empty on a day where the best published prediction sat at, say, 0.60, even
    // though real published predictions existed. These two sections must show the best signal
    // available regardless of that floor; only Top Intelligence applies it (see
    // top-ai-intelligence.tsx).
    const picks = [
      pick({ id: 'low', subject_ref: 'fixture-1', confidence_composite: 0.3 }),
      pick({ id: 'below-ai-picks-floor', subject_ref: 'fixture-2', confidence_composite: 0.6 }),
      pick({ id: 'high', subject_ref: 'fixture-3', confidence_composite: 0.9 }),
    ]

    const result = rankPicks(picks)

    expect(result.map((p) => p.id)).toEqual(['high', 'below-ai-picks-floor', 'low'])
  })

  it('deduplicates by fixture before ranking', () => {
    const picks = [
      pick({ id: 'a-low', subject_ref: 'fixture-1', confidence_composite: 0.4 }),
      pick({ id: 'b-high', subject_ref: 'fixture-2', confidence_composite: 0.8 }),
      pick({ id: 'a-high', subject_ref: 'fixture-1', confidence_composite: 0.7 }),
    ]

    const result = rankPicks(picks)

    // 'a-high' never even reaches ranking — dedupeByFixture already dropped it in favor of the
    // first 'fixture-1' entry ('a-low'), same as the real API's pre-sorted-by-confidence contract.
    expect(result.map((p) => p.id)).toEqual(['b-high', 'a-low'])
  })
})
