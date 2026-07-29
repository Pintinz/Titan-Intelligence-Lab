import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, api } from '@/lib/api/client'

vi.mock('@/lib/supabase', () => ({
  supabase: {
    auth: {
      getSession: vi.fn().mockResolvedValue({ data: { session: { access_token: 'test-token' } } }),
    },
  },
}))

const originalFetch = global.fetch

afterEach(() => {
  global.fetch = originalFetch
  vi.restoreAllMocks()
})

describe('api client', () => {
  it('unwraps the {data, meta, error} envelope on success', async () => {
    global.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ data: { id: '1' }, meta: {}, error: null }), { status: 200 }),
    )

    const result = await api.get<{ id: string }>('/api/v1/whatever')

    expect(result).toEqual({ id: '1' })
  })

  it('attaches the Supabase session token as a Bearer header', async () => {
    global.fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ data: [], meta: {}, error: null })))

    await api.get('/api/v1/whatever')

    const [, init] = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0]
    expect(init.headers.Authorization).toBe('Bearer test-token')
  })

  it('serializes query params, skipping undefined/null/empty', async () => {
    global.fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ data: [], meta: {}, error: null })))

    await api.get('/api/v1/whatever', { limit: 10, status: undefined, query: '' })

    const [url] = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0]
    expect(url).toBe('http://localhost:8000/api/v1/whatever?limit=10')
  })

  it('throws ApiError with the parsed detail on a non-2xx response', async () => {
    global.fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: 'not found' }), { status: 404 }))

    await expect(api.get('/api/v1/missing')).rejects.toMatchObject(
      new ApiError(404, 'not found'),
    )
  })

  it('falls back to statusText when the error body is not JSON', async () => {
    global.fetch = vi.fn().mockResolvedValue(new Response('not json', { status: 500, statusText: 'Server Error' }))

    await expect(api.get('/api/v1/broken')).rejects.toMatchObject({ status: 500 })
  })
})
