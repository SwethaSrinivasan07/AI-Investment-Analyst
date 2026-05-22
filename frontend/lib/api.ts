const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export interface ThinkingBlock {
  type: 'thinking'
  thinking: string
}

export interface Source {
  text: string
  doc_type: string  // "10-K" | "10-Q" | "8-K"
  filing_date: string
  chunk_id?: string
}

export interface EvalScores {
  data_grounding: number
  thesis_clarity: number
  risk_depth: number
  valuation_rigor: number
  actionability: number
  overall: number
  rationale: Record<string, string>
}

export interface UsageStats {
  input_tokens: number
  output_tokens: number
  cache_read_tokens: number
  cache_creation_tokens: number
  estimated_cost_usd: number
}

export interface Memo {
  id: string
  ticker: string
  company_name: string
  strategy: string
  sector: string
  recommendation: string
  conviction: string
  markdown_text: string
  thinking_trace: ThinkingBlock[] | null
  sources: Source[] | null
  eval_scores: EvalScores | null
  usage_stats: UsageStats | null
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
  numPicks?: number,
  ticker?: string,
): Promise<Memo> {
  const res = await fetch(`${API_URL}/api/memos/generate`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({
      strategy,
      sector,
      ...(numPicks != null ? { num_picks: numPicks } : {}),
      ...(ticker ? { ticker } : {}),
    }),
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

export function streamMemoGeneration(strategy: string, sector: string, ticker?: string): EventSource {
  const token = getToken()
  const url = new URL(`${API_URL}/api/memos/generate/stream`)
  url.searchParams.set('strategy', strategy)
  url.searchParams.set('sector', sector)
  if (ticker) url.searchParams.set('ticker', ticker)
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

// ── Portfolio ──────────────────────────────────────────────────────────────────

export interface PortfolioPosition {
  id: string
  ticker: string
  company_name: string | null
  shares: number
  cost_basis: number
  current_price: number
  market_value: number
  cost_value: number
  gain_loss: number
  gain_loss_pct: number
  price_change_1d_pct: number
  signal: 'Hold' | 'Trim' | 'Add'
  signal_rationale: string
  added_at: string
}

export interface PortfolioSummary {
  total_value: number
  total_cost: number
  total_gain_loss: number
  total_gain_loss_pct: number
  position_count: number
}

export interface PortfolioResponse {
  positions: PortfolioPosition[]
  summary: PortfolioSummary
}

export interface AddPositionRequest {
  ticker: string
  shares: number
  cost_basis: number
}

export async function getPortfolio(): Promise<PortfolioResponse> {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 90_000)
  try {
    const res = await fetch(`${API_URL}/api/portfolio`, {
      headers: authHeaders(),
      signal: controller.signal,
    })
    return handleResponse<PortfolioResponse>(res)
  } catch (err) {
    if (err instanceof Error && err.name === 'AbortError') {
      throw new Error('Portfolio load timed out. Please refresh.')
    }
    throw err
  } finally {
    clearTimeout(timeout)
  }
}

export async function seedPortfolio(): Promise<{ detail: string }> {
  const res = await fetch(`${API_URL}/api/portfolio/seed`, {
    method: 'POST',
    headers: authHeaders(),
  })
  return handleResponse<{ detail: string }>(res)
}

export async function addPosition(req: AddPositionRequest): Promise<PortfolioPosition> {
  const res = await fetch(`${API_URL}/api/portfolio/positions`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(req),
  })
  return handleResponse<PortfolioPosition>(res)
}

export async function deletePosition(id: string): Promise<void> {
  const res = await fetch(`${API_URL}/api/portfolio/positions/${id}`, {
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

// ── Backtests ─────────────────────────────────────────────────────────────────

export interface BacktestMetrics {
  cumulative_return_pct: number
  annualized_return_pct: number
  sharpe_ratio: number
  max_drawdown_pct: number
  win_rate_pct: number
  alpha_vs_spy_pct: number
  volatility_pct: number
}

export interface BacktestResult {
  id: string
  strategy: string
  sector: string
  period: string
  metrics: BacktestMetrics
  chart_data: Array<{ date: string; portfolio: number; spy: number; sector_etf: number }>
  created_at: string
}

export async function runBacktest(
  strategy: string,
  sector: string,
  period: string
): Promise<BacktestResult> {
  const res = await fetch(`${API_URL}/api/backtests/run`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({ strategy, sector, period }),
  })
  return handleResponse<BacktestResult>(res)
}

export async function getBacktests(): Promise<BacktestResult[]> {
  const res = await fetch(`${API_URL}/api/backtests`, {
    headers: authHeaders(),
  })
  return handleResponse<BacktestResult[]>(res)
}

export async function getBacktest(id: string): Promise<BacktestResult> {
  const res = await fetch(`${API_URL}/api/backtests/${id}`, {
    headers: authHeaders(),
  })
  return handleResponse<BacktestResult>(res)
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

// ── Settings ──────────────────────────────────────────────────────────────────

export interface Schedule {
  id: string
  strategy: string
  sector: string
  frequency: string
  enabled: boolean
  next_run_at: string | null
  created_at: string
}

export interface UserSettings {
  email: string
  preferences: Record<string, unknown>
  schedules: Schedule[]
}

export async function getSettings(): Promise<UserSettings> {
  const res = await fetch(`${API_URL}/api/settings`, {
    headers: authHeaders(),
  })
  return handleResponse<UserSettings>(res)
}

export async function updatePreferences(
  prefs: Record<string, unknown>
): Promise<UserSettings> {
  const res = await fetch(`${API_URL}/api/settings/preferences`, {
    method: 'PUT',
    headers: authHeaders(),
    body: JSON.stringify(prefs),
  })
  return handleResponse<UserSettings>(res)
}

export async function createSchedule(
  strategy: string,
  sector: string,
  frequency: string
): Promise<Schedule> {
  const res = await fetch(`${API_URL}/api/settings/schedules`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({ strategy, sector, frequency }),
  })
  return handleResponse<Schedule>(res)
}

export async function updateSchedule(
  id: string,
  updates: { enabled?: boolean; frequency?: string }
): Promise<Schedule> {
  const res = await fetch(`${API_URL}/api/settings/schedules/${id}`, {
    method: 'PUT',
    headers: authHeaders(),
    body: JSON.stringify(updates),
  })
  return handleResponse<Schedule>(res)
}

export async function deleteSchedule(id: string): Promise<void> {
  const res = await fetch(`${API_URL}/api/settings/schedules/${id}`, {
    method: 'DELETE',
    headers: authHeaders(),
  })
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
}

// ── Portfolio Alerts ──────────────────────────────────────────────────────────

export interface PortfolioAlert {
  id: string
  ticker: string | null
  alert_type: 'price_move' | 'news' | 'signal' | 'opportunity'
  severity: 'info' | 'warning' | 'action'
  title: string
  message: string
  data: Record<string, unknown>
  read: boolean
  created_at: string
}

export async function getAlerts(unreadOnly = false): Promise<PortfolioAlert[]> {
  const url = `${API_URL}/api/portfolio/alerts${unreadOnly ? '?unread_only=true' : ''}`
  const res = await fetch(url, { headers: authHeaders() })
  return handleResponse<PortfolioAlert[]>(res)
}

export async function markAlertRead(id: string): Promise<void> {
  const res = await fetch(`${API_URL}/api/portfolio/alerts/${id}/read`, {
    method: 'POST',
    headers: authHeaders(),
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
}

export async function markAllAlertsRead(): Promise<void> {
  const res = await fetch(`${API_URL}/api/portfolio/alerts/read-all`, {
    method: 'POST',
    headers: authHeaders(),
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
}

export async function triggerMonitorRun(): Promise<{ detail: string }> {
  const res = await fetch(`${API_URL}/api/portfolio/alerts/run`, {
    method: 'POST',
    headers: authHeaders(),
  })
  return handleResponse<{ detail: string }>(res)
}

// ── Portfolio Orders ───────────────────────────────────────────────────────────

export interface PortfolioOrder {
  id: string
  ticker: string
  side: 'buy' | 'sell'
  qty: number
  order_type: string
  status: string
  alpaca_order_id: string | null
  filled_price: number | null
  source: string
  rationale: string | null
  created_at: string
  filled_at: string | null
}

export interface AlpacaStatus {
  configured: boolean
  mode: 'paper' | 'live' | 'not_configured'
}

export async function getOrders(): Promise<PortfolioOrder[]> {
  const res = await fetch(`${API_URL}/api/portfolio/orders`, { headers: authHeaders() })
  return handleResponse<PortfolioOrder[]>(res)
}

export async function placeOrder(
  ticker: string,
  side: 'buy' | 'sell',
  qty: number,
  rationale?: string
): Promise<PortfolioOrder> {
  const res = await fetch(`${API_URL}/api/portfolio/orders`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({ ticker, side, qty, rationale }),
  })
  return handleResponse<PortfolioOrder>(res)
}

export async function getAlpacaStatus(): Promise<AlpacaStatus> {
  const res = await fetch(`${API_URL}/api/portfolio/alpaca/status`, { headers: authHeaders() })
  return handleResponse<AlpacaStatus>(res)
}

export async function importPortfolioCSV(file: File): Promise<{ imported: number; detail: string }> {
  const formData = new FormData()
  formData.append('file', file)
  const token = getToken()
  const headers: HeadersInit = token ? { Authorization: `Bearer ${token}` } : {}
  const res = await fetch(`${API_URL}/api/portfolio/import`, {
    method: 'POST',
    headers,
    body: formData,
  })
  return handleResponse<{ imported: number; detail: string }>(res)
}

// ── Memo Stats ────────────────────────────────────────────────────────────────

export interface MemoStats {
  total_memos: number
  memos_with_sources: number
  grounding_rate_pct: number
  avg_eval_scores: Record<string, number | null>
  token_usage: {
    memos_tracked: number
    total_input_tokens: number
    total_output_tokens: number
    total_cache_read_tokens: number
    total_cache_creation_tokens: number
    total_estimated_cost_usd: number
    avg_cost_per_memo_usd: number | null
    cache_savings_pct: number | null
  }
  eval_score_trend: Array<{
    memo_id: string
    ticker: string
    created_at: string
    overall: number | null
  }>
}

export async function getMemoStats(): Promise<MemoStats> {
  const res = await fetch(`${API_URL}/api/memos/stats`, {
    headers: authHeaders(),
  })
  return handleResponse<MemoStats>(res)
}
