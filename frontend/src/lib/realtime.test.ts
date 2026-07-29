import { describe, expect, it, vi } from 'vitest'
import { REALTIME_TABLES, subscribeToTable } from '@/lib/realtime'

const mockChannel = {
  on: vi.fn().mockReturnThis(),
  subscribe: vi.fn().mockReturnThis(),
}

vi.mock('@/lib/supabase', () => ({
  supabase: {
    channel: vi.fn(() => mockChannel),
    removeChannel: vi.fn(),
  },
}))

describe('REALTIME_TABLES', () => {
  it('covers all 12 Realtime-published tables from migrations 0014 and 0019', () => {
    expect(Object.keys(REALTIME_TABLES)).toHaveLength(12)
  })

  it('maps each key to a schema and table name', () => {
    expect(REALTIME_TABLES.predictions).toEqual({ schema: 'predictions', table: 'predictions' })
    expect(REALTIME_TABLES.matches).toEqual({ schema: 'sports', table: 'matches' })
  })
})

describe('subscribeToTable', () => {
  it('subscribes to a postgres_changes event on the resolved schema/table', async () => {
    const { supabase } = await import('@/lib/supabase')
    subscribeToTable('predictions', () => {})

    expect(supabase.channel).toHaveBeenCalledWith('predictions:predictions')
    expect(mockChannel.on).toHaveBeenCalledWith(
      'postgres_changes',
      expect.objectContaining({ event: '*', schema: 'predictions', table: 'predictions' }),
      expect.any(Function),
    )
  })

  it('returns an unsubscribe function that removes the channel', async () => {
    const { supabase } = await import('@/lib/supabase')
    const unsubscribe = subscribeToTable('syncRuns', () => {})
    unsubscribe()
    expect(supabase.removeChannel).toHaveBeenCalled()
  })
})
