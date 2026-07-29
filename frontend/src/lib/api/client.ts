import { supabase } from '@/lib/supabase'
import { env } from '@/lib/env'

/**
 * TitanIQ backend response envelope (apps/api/*.py `envelope()` helper) — success responses are
 * always `{data, meta, error}`; failures are plain FastAPI `{detail}` with a non-2xx status (no
 * shared exception handler unifies the two shapes on the backend, so this client normalizes both
 * into `ApiError` on the failure path rather than assuming a consistent envelope everywhere).
 */
export interface Envelope<T> {
  data: T
  meta: Record<string, unknown>
  error: unknown
}

export class ApiError extends Error {
  status: number
  detail: string

  constructor(status: number, detail: string) {
    super(detail)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

async function authHeader(): Promise<Record<string, string>> {
  const { data } = await supabase.auth.getSession()
  const token = data.session?.access_token
  return token ? { Authorization: `Bearer ${token}` } : {}
}

function withQuery(path: string, params?: Record<string, unknown>): string {
  if (!params) return path
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue
    search.set(key, String(value))
  }
  const qs = search.toString()
  return qs ? `${path}?${qs}` : path
}

const REQUEST_TIMEOUT_MS = 20_000

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const auth = await authHeader()
  let response: Response
  try {
    response = await fetch(`${env.apiBaseUrl}${path}`, {
      ...init,
      signal: init.signal ?? AbortSignal.timeout(REQUEST_TIMEOUT_MS),
      headers: {
        'Content-Type': 'application/json',
        ...auth,
        ...init.headers,
      },
    })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'TimeoutError') {
      throw new ApiError(0, 'The request timed out. Check your connection and try again.')
    }
    throw new ApiError(0, 'Could not reach the server. Check your connection and try again.')
  }

  if (!response.ok) {
    let detail = response.statusText
    try {
      const body = await response.json()
      detail = typeof body?.detail === 'string' ? body.detail : JSON.stringify(body)
    } catch {
      // non-JSON error body — keep statusText
    }
    throw new ApiError(response.status, detail)
  }

  if (response.status === 204) return undefined as T
  const envelope = (await response.json()) as Envelope<T>
  return envelope.data
}

export const api = {
  get: <T>(path: string, params?: Record<string, unknown>) => request<T>(withQuery(path, params)),
  post: <T>(path: string, body?: unknown, params?: Record<string, unknown>) =>
    request<T>(withQuery(path, params), {
      method: 'POST',
      body: body !== undefined ? JSON.stringify(body) : undefined,
    }),
  delete: <T>(path: string, body?: unknown, params?: Record<string, unknown>) =>
    request<T>(withQuery(path, params), {
      method: 'DELETE',
      body: body !== undefined ? JSON.stringify(body) : undefined,
    }),
}
