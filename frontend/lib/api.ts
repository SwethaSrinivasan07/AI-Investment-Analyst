const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export interface Memo {
  id: string
  ticker: string
  company_name: string
  strategy: string
  sector: string
  recommendation: string
  conviction: string
  markdown_text: string
  thinking_trace: unknown[]
  sources: unknown[]
  eval_scores: Record<string, number> | null
  data_as_of: string
  created_at: string
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  created_at: string
}

export interface AuthResponse {
  access_token: string
  token_type: string
  user: {
    id: string
    email: string
    preferences?: Record<string, unknown>
  }
}

export interface UserProfile {
  id: string
  email: string
  preferences?: Record<string, unknown>
}

function getToken(): string | null {
  if (typeof window === 'undefined') return null
  return localStorage.getItem('alphalens_token')
}

export function setToken(token: string): void {
  if (typeof window === 'undefined') return
  localStorage.setItem('alphalens_token', token)
}

export function clearToken(): void {
  if (typeof window === 'undefined') return
  localStorage.removeItem('alphalens_token')
}

export function hasToken(): boolean {
  return getToken() !== null
}

function authHeaders(): HeadersInit {
  const token = getToken()
  return token
    ? { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }
    : { 'Content-Type': 'application/json' }
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let message = `HTTP ${res.status}`
    try {
      const body = await res.json()
      message = body.detail ?? body.message ?? message
    } catch {
      // ignore parse error
    }
    throw new Error(message)
  }
  return res.json() as Promise<T>
}

// ── Auth ──────────────────────────────────────────────────────────────────────

export async function login(email: string, password: string): Promise<AuthResponse> {
  const res = await fetch(`${API_URL}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
  return handleResponse<AuthResponse>(res)
}

export async function register(email: string, password: string): Promise<AuthResponse> {
  const res = await fetch(`${API_URL}/api/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
  return handleResponse<AuthResponse>(res)
}

export async function getMe(): Promise<UserProfile> {
  const res = await fetch(`${API_URL}/api/auth/me`, {
    headers: authHeaders(),
  })
  return handleResponse<UserProfile>(res)
}

// ── Memos ─────────────────────────────────────────────────────────────────────

export async function getMemos(): Promise<Memo[]> {
  const res = await fetch(`${API_URL}/api/memos`, {
    headers: authHeaders(),
  })
  return handleResponse<Memo[]>(res)
}

export async function getMemo(id: string): Promise<Memo> {
  const res = await fetch(`${API_URL}/api/memos/${id}`, {
    headers: authHeaders(),
  })
  return handleResponse<Memo>(res)
}

export async function generateMemo(
  strategy: string,
  sector: string,
  numPicks?: number
): Promise<Memo> {
  const res = await fetch(`${API_URL}/api/memos/generate`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({ strategy, sector, ...(numPicks != null ? { num_picks: numPicks } : {}) }),
  })
  return handleResponse<Memo>(res)
}

export async function deleteMemo(id: string): Promise<void> {
  const res = await fetch(`${API_URL}/api/memos/${id}`, {
    method: 'DELETE',
    headers: authHeaders(),
  })
  if (!res.ok) {
    let message = `HTTP ${res.status}`
    try {
      const body = await res.json()
      message = body.detail ?? body.message ?? message
    } catch {
      // ignore
    }
    throw new Error(message)
  }
}

export function streamMemoGeneration(strategy: string, sector: string): EventSource {
  const token = getToken()
  const url = new URL(`${API_URL}/api/memos/generate/stream`)
  url.searchParams.set('strategy', strategy)
  url.searchParams.set('sector', sector)
  if (token) url.searchParams.set('token', token)
  return new EventSource(url.toString())
}

// ── Chat ──────────────────────────────────────────────────────────────────────

export async function getChatHistory(memoId: string): Promise<ChatMessage[]> {
  const res = await fetch(`${API_URL}/api/chat/${memoId}/history`, {
    headers: authHeaders(),
  })
  return handleResponse<ChatMessage[]>(res)
}

export async function* streamChatFetch(
  memoId: string,
  message: string
): AsyncGenerator<string> {
  const response = await fetch(`${API_URL}/api/chat/${memoId}`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({ message }),
  })

  if (!response.ok) {
    let errMsg = `HTTP ${response.status}`
    try {
      const body = await response.json()
      errMsg = body.detail ?? body.message ?? errMsg
    } catch {
      // ignore
    }
    throw new Error(errMsg)
  }

  const reader = response.body!.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    // keep last potentially incomplete line in buffer
    buffer = lines.pop() ?? ''

    for (const line of lines) {
      const trimmed = line.trim()
      if (!trimmed.startsWith('data:')) continue
      const jsonStr = trimmed.slice('data:'.length).trim()
      if (!jsonStr) continue
      try {
        const parsed = JSON.parse(jsonStr) as { type: string; content?: string }
        if (parsed.type === 'token' && parsed.content) {
          yield parsed.content
        } else if (parsed.type === 'done') {
          return
        }
      } catch {
        // malformed SSE line — skip
      }
    }
  }

  // flush any remaining buffer
  if (buffer.trim().startsWith('data:')) {
    const jsonStr = buffer.trim().slice('data:'.length).trim()
    try {
      const parsed = JSON.parse(jsonStr) as { type: string; content?: string }
      if (parsed.type === 'token' && parsed.content) {
        yield parsed.content
      }
    } catch {
      // ignore
    }
  }
}

// Legacy EventSource-based streaming (GET-only, token via query param)
export function streamChat(
  memoId: string,
  _message: string
): { eventSource: EventSource; cleanup: () => void } {
  const token = getToken()
  const url = new URL(`${API_URL}/api/chat/${memoId}/stream`)
  if (token) url.searchParams.set('token', token)
  const eventSource = new EventSource(url.toString())
  const cleanup = () => eventSource.close()
  return { eventSource, cleanup }
}
